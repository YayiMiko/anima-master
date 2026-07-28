from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - requests is expected in AstrBot env.
    requests = None


CHARACTER_CATEGORY = 4

DEFAULT_DONMAI_BASE_URLS = (
    "https://safebooru.donmai.us",
    "https://danbooru.donmai.us",
)
DEFAULT_SAFEBOORU_DAPI_URL = "https://safebooru.org/index.php"
DEFAULT_USER_AGENT = "AstrBotComfyUIAgent/0.13"

KNOWN_CORE_ALIASES: dict[str, tuple[str, ...]] = {
    "忍野忍": ("oshino_shinobu", "shinobu_oshino"),
    "洛茜": ("rossi_(arknights)", "rossi_(arknights:endfield)", "rossi"),
    "妃咲": ("kisaki_(blue_archive)", "kisaki", "hisaki_(blue_archive)", "hisaki"),
    "Kisaki": ("kisaki_(blue_archive)", "kisaki", "hisaki_(blue_archive)", "hisaki"),
    "kisaki": ("kisaki_(blue_archive)", "kisaki", "hisaki_(blue_archive)", "hisaki"),
    "キサキ": ("kisaki_(blue_archive)", "kisaki", "hisaki_(blue_archive)", "hisaki"),
    "铃兰": ("suzuran_(arknights)", "suzuran"),
    "鈴蘭": ("suzuran_(arknights)", "suzuran"),
    "Suzuran": ("suzuran_(arknights)", "suzuran"),
    "suzuran": ("suzuran_(arknights)", "suzuran"),
}
KNOWN_CANONICAL_CORE_TAGS: dict[str, str] = {
    "shinobu_oshino": "oshino_shinobu",
    "rossi": "rossi_(arknights)",
    "rossi_(arknights:endfield)": "rossi_(arknights)",
    "kisaki": "kisaki_(blue_archive)",
    "hisaki": "kisaki_(blue_archive)",
    "hisaki_(blue_archive)": "kisaki_(blue_archive)",
    "suzuran": "suzuran_(arknights)",
}

GENERAL_TAG_WORDS = {
    "arms",
    "background",
    "belt",
    "black",
    "blonde",
    "blue",
    "boots",
    "boy",
    "bow",
    "breasts",
    "brown",
    "cape",
    "choker",
    "dress",
    "ear",
    "ears",
    "eye",
    "eyes",
    "fang",
    "frill",
    "frilled",
    "gloves",
    "gold",
    "green",
    "grey",
    "hair",
    "hat",
    "hood",
    "jacket",
    "large",
    "long",
    "looking",
    "medium",
    "pale",
    "pink",
    "purple",
    "red",
    "ribbon",
    "shirt",
    "short",
    "skirt",
    "sleeves",
    "small",
    "smile",
    "solo",
    "standing",
    "stockings",
    "thighhighs",
    "trim",
    "white",
    "yellow",
    "girl",
    "cloak",
    "young",
}


@dataclass(frozen=True)
class TagRecord:
    name: str
    category: int
    post_count: int
    deprecated: bool = False
    source: str = ""


@dataclass(frozen=True)
class CoreTagResolution:
    text: str
    replacements: tuple[tuple[str, str, int, str], ...]
    inserted: tuple[tuple[str, int, str], ...]
    verified: tuple[tuple[str, int, str], ...] = ()


def required_core_tags_for_prompt(user_prompt: str) -> tuple[str, ...]:
    """Return locally known character anchors explicitly requested by the user."""
    text = str(user_prompt or "")
    anchors: list[str] = []
    for alias, queries in KNOWN_CORE_ALIASES.items():
        if alias not in text:
            continue
        record = _known_canonical_record(list(queries))
        if record and record.name not in anchors:
            anchors.append(record.name)
    return tuple(anchors)


def _split_tags(text: str) -> list[str]:
    cleaned = str(text or "")
    cleaned = cleaned.replace("，", ",").replace("、", ",").replace(";", ",")
    cleaned = cleaned.replace("\n", ",")
    cleaned = re.sub(
        r"^(?:positive|prompt|tags|提示词|正向提示词)\s*[:：]",
        "",
        cleaned.strip(),
        flags=re.I,
    )
    parts = [part.strip(" \t\r\n,.;:：") for part in cleaned.split(",")]
    return [part for part in parts if part]


def _normalize_query(tag: str) -> str:
    value = str(tag or "").strip().lower()
    value = re.sub(r":\s*[\d.]+$", "", value)
    value = value.strip(" []{}")
    if (
        value.startswith("(")
        and value.endswith(")")
        and value.count("(") == 1
        and value.count(")") == 1
    ):
        value = value[1:-1].strip()
    value = re.sub(r"\s+", "_", value)
    return value


def _candidate_queries(tag: str) -> list[str]:
    query = _normalize_query(tag)
    if not query:
        return []
    queries = [query]
    parenthesized = re.match(r"^([a-z0-9_.'-]+)_\([^)]+\)$", query)
    if parenthesized:
        queries.append(parenthesized.group(1))
    if "(" not in query and ")" not in query:
        parts = [part for part in query.split("_") if part]
        if len(parts) == 2 and all(part not in GENERAL_TAG_WORDS for part in parts):
            queries.append(f"{parts[1]}_{parts[0]}")
    deduped: list[str] = []
    for item in queries:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _looks_like_core_tag(tag: str) -> bool:
    raw = str(tag or "").strip()
    if " " in raw and "(" not in raw and ")" not in raw:
        return False
    query = _normalize_query(tag)
    if not re.fullmatch(r"[a-z0-9_():.'-]{3,80}", query):
        return False
    if query.startswith("@"):
        return False
    if "_" not in query and "(" not in query:
        return False
    compact = query.replace("(", "_").replace(")", "_")
    parts = [part for part in compact.split("_") if part]
    if not parts or all(part in GENERAL_TAG_WORDS for part in parts):
        return False
    if parts[-1] in GENERAL_TAG_WORDS:
        return False
    if any(
        part in {"hair", "eyes", "dress", "skirt", "background", "smile"}
        for part in parts
    ):
        return False
    return True


def _http_get_json(
    url: str, *, params: dict[str, Any], timeout: float, user_agent: str
) -> Any:
    if requests is None:
        return None
    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    if response.status_code != 200:
        return None
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type and not response.text.lstrip().startswith(("[", "{")):
        return None
    return response.json()


def _fetch_donmai_tag(
    base_url: str, query: str, *, timeout: float, user_agent: str
) -> list[TagRecord]:
    data = _http_get_json(
        base_url.rstrip("/") + "/tags.json",
        params={"search[name_matches]": query, "limit": 10},
        timeout=timeout,
        user_agent=user_agent,
    )
    if not isinstance(data, list):
        return []
    records: list[TagRecord] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        records.append(
            TagRecord(
                name=name,
                category=int(item.get("category") or 0),
                post_count=int(item.get("post_count") or 0),
                deprecated=bool(item.get("is_deprecated")),
                source=base_url,
            )
        )
    return records


def _fetch_donmai_autocomplete(
    base_url: str,
    query: str,
    *,
    timeout: float,
    user_agent: str,
) -> list[TagRecord]:
    data = _http_get_json(
        base_url.rstrip("/") + "/autocomplete.json",
        params={"search[type]": "tag_query", "search[query]": query},
        timeout=timeout,
        user_agent=user_agent,
    )
    if not isinstance(data, list):
        return []
    records: list[TagRecord] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag") if isinstance(item.get("tag"), dict) else item
        name = str(item.get("value") or tag.get("name") or "").strip()
        if not name:
            continue
        records.append(
            TagRecord(
                name=name,
                category=int(item.get("category") or tag.get("category") or 0),
                post_count=int(item.get("post_count") or tag.get("post_count") or 0),
                deprecated=bool(tag.get("is_deprecated")),
                source=base_url + "/autocomplete",
            )
        )
    return records


def _fetch_safebooru_dapi_tag(
    query: str,
    *,
    timeout: float,
    user_agent: str,
) -> list[TagRecord]:
    """Fetch an exact tag from the Safebooru-compatible read-only DAPI.

    Args:
        query: Normalized tag name to query.
        timeout: HTTP request timeout in seconds.
        user_agent: User-Agent header value.

    Returns:
        Parsed tag records, or an empty list when the request is unavailable.
    """
    if requests is None:
        return []
    try:
        response = requests.get(
            DEFAULT_SAFEBOORU_DAPI_URL,
            params={
                "page": "dapi",
                "s": "tag",
                "q": "index",
                "name": query,
            },
            timeout=timeout,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/xml,text/xml,*/*",
            },
        )
        if response.status_code != 200:
            return []
        root = ET.fromstring(response.text)
    except Exception:
        return []

    records: list[TagRecord] = []
    for item in root.findall("tag"):
        name = str(item.attrib.get("name") or "").strip()
        if not name:
            continue
        try:
            category = int(item.attrib.get("type") or 0)
            post_count = int(item.attrib.get("count") or 0)
        except (TypeError, ValueError):
            continue
        records.append(
            TagRecord(
                name=name,
                category=category,
                post_count=post_count,
                source="https://safebooru.org/dapi",
            )
        )
    return records


def _fetch_tag_records(
    query: str,
    *,
    donmai_base_urls: tuple[str, ...],
    timeout: float,
    user_agent: str,
    cache: dict[str, Any],
) -> list[TagRecord]:
    query = _normalize_query(query)
    if not query:
        return []
    cached = cache.get(query)
    if isinstance(cached, tuple) and len(cached) == 2:
        cached_at, cached_records = cached
        ttl = 3600.0 if cached_records else 60.0
        if time.monotonic() - float(cached_at) < ttl:
            return list(cached_records)
    elif isinstance(cached, list):
        return cached

    records: list[TagRecord] = []
    for base_url in donmai_base_urls:
        records = _fetch_donmai_tag(
            base_url, query, timeout=timeout, user_agent=user_agent
        )
        if records:
            break
    if not records:
        records = _fetch_safebooru_dapi_tag(
            query,
            timeout=timeout,
            user_agent=user_agent,
        )
    cache[query] = (time.monotonic(), records)
    return records


def _fetch_autocomplete_records(
    query: str,
    *,
    donmai_base_urls: tuple[str, ...],
    timeout: float,
    user_agent: str,
    cache: dict[str, Any],
) -> list[TagRecord]:
    query = _normalize_query(query)
    if not query:
        return []
    cache_key = f"autocomplete:{query}"
    cached = cache.get(cache_key)
    if isinstance(cached, tuple) and len(cached) == 2:
        cached_at, cached_records = cached
        ttl = 3600.0 if cached_records else 60.0
        if time.monotonic() - float(cached_at) < ttl:
            return list(cached_records)
    elif isinstance(cached, list):
        return cached

    records: list[TagRecord] = []
    for base_url in donmai_base_urls:
        records = _fetch_donmai_autocomplete(
            base_url,
            query,
            timeout=timeout,
            user_agent=user_agent,
        )
        if records:
            break
    cache[cache_key] = (time.monotonic(), records)
    return records


def _best_character(
    queries: list[str],
    *,
    donmai_base_urls: tuple[str, ...],
    timeout: float,
    user_agent: str,
    cache: dict[str, Any],
    use_autocomplete: bool = False,
) -> TagRecord | None:
    records: list[TagRecord] = []
    for query in queries:
        records.extend(
            _fetch_tag_records(
                query,
                donmai_base_urls=donmai_base_urls,
                timeout=timeout,
                user_agent=user_agent,
                cache=cache,
            )
        )
    if use_autocomplete:
        for query in queries:
            records.extend(
                _fetch_autocomplete_records(
                    query,
                    donmai_base_urls=donmai_base_urls,
                    timeout=timeout,
                    user_agent=user_agent,
                    cache=cache,
                )
            )
    characters = [
        record
        for record in records
        if record.category == CHARACTER_CATEGORY and not record.deprecated
    ]
    if characters:
        return max(characters, key=lambda record: record.post_count)
    return None


def _known_canonical_record(queries: list[str]) -> TagRecord | None:
    for query in queries:
        canonical = KNOWN_CANONICAL_CORE_TAGS.get(_normalize_query(query))
        if canonical:
            return TagRecord(
                name=canonical,
                category=CHARACTER_CATEGORY,
                post_count=0,
                deprecated=False,
                source="local_alias",
            )
    return None


def _user_character_queries(user_prompt: str) -> list[str]:
    """Extract likely explicitly named characters from the raw user request.

    Args:
        user_prompt: Original natural-language request.

    Returns:
        A small ordered list of names suitable for autocomplete lookup.
    """
    text = str(user_prompt or "")
    queries: list[str] = []
    for match in re.finditer(
        r"(?:画|生成|绘制|来一张|生图)?\s*"
        r"([\u4e00-\u9fffぁ-んァ-ヶ]{2,12}?)"
        r"(?=穿|戴|拿|手持|站|坐|躺|跑|看|和|与|，|,|\s|$)",
        text,
    ):
        name = match.group(1).strip()
        name = re.sub(r"^(?:一个|一位|角色|人物|少女|女孩)", "", name)
        if name.startswith(("穿", "戴", "拿", "手持", "站", "坐", "躺", "跑", "看")):
            continue
        if 2 <= len(name) <= 12 and name not in queries:
            queries.append(name)
        if len(queries) >= 2:
            break
    return queries


def resolve_core_tags(
    text: str,
    *,
    user_prompt: str = "",
    allow_insert: bool = False,
    max_candidates: int = 6,
    timeout: float = 6.0,
    donmai_base_urls: tuple[str, ...] = DEFAULT_DONMAI_BASE_URLS,
    user_agent: str = DEFAULT_USER_AGENT,
    cache: dict[str, Any] | None = None,
) -> CoreTagResolution:
    tag_cache = cache if cache is not None else {}
    tags = _split_tags(text)
    replacements: list[tuple[str, str, int, str]] = []
    inserted: list[tuple[str, int, str]] = []
    verified: list[tuple[str, int, str]] = []

    candidate_indexes: list[int] = []
    for index, tag in enumerate(tags[: max(max_candidates * 3, 12)]):
        if _looks_like_core_tag(tag):
            candidate_indexes.append(index)
        if len(candidate_indexes) >= max_candidates:
            break

    for index in candidate_indexes:
        original = tags[index]
        queries = _candidate_queries(original)
        best = _known_canonical_record(queries) or _best_character(
            queries,
            donmai_base_urls=donmai_base_urls,
            timeout=timeout,
            user_agent=user_agent,
            cache=tag_cache,
            use_autocomplete=False,
        )
        original_key = _normalize_query(original)
        if not best:
            continue
        verified.append((best.name, best.post_count, best.source))
        if best.name != original_key or best.name != original.strip():
            tags[index] = best.name
            replacements.append((original, best.name, best.post_count, best.source))
        break

    if allow_insert:
        existing = {_normalize_query(tag) for tag in tags}
        for alias, queries in KNOWN_CORE_ALIASES.items():
            if alias not in user_prompt:
                continue
            alias_queries = list(queries)
            best = _known_canonical_record(alias_queries) or _best_character(
                alias_queries,
                donmai_base_urls=donmai_base_urls,
                timeout=timeout,
                user_agent=user_agent,
                cache=tag_cache,
                use_autocomplete=True,
            )
            if not best:
                continue
            alias_keys = {_normalize_query(query) for query in alias_queries}
            replaced = False
            for index, tag in enumerate(tags):
                if (
                    _normalize_query(tag) not in alias_keys
                    or _normalize_query(tag) == best.name
                ):
                    continue
                old = tags[index]
                tags[index] = best.name
                replacements.append((old, best.name, best.post_count, best.source))
                existing.discard(_normalize_query(old))
                existing.add(best.name)
                replaced = True
                break
            if not replaced and best.name not in existing:
                tags.insert(0, best.name)
                existing.add(best.name)
                inserted.append((best.name, best.post_count, best.source))

        if not inserted:
            for raw_name in _user_character_queries(user_prompt):
                best = _best_character(
                    [raw_name],
                    donmai_base_urls=donmai_base_urls,
                    timeout=timeout,
                    user_agent=user_agent,
                    cache=tag_cache,
                    use_autocomplete=True,
                )
                if not best or best.name in existing:
                    continue
                if candidate_indexes:
                    index = candidate_indexes[0]
                    old = tags[index]
                    tags[index] = best.name
                    existing.discard(_normalize_query(old))
                    existing.add(best.name)
                    replacements.append((old, best.name, best.post_count, best.source))
                else:
                    tags.insert(0, best.name)
                    existing.add(best.name)
                    inserted.append((best.name, best.post_count, best.source))
                break

    return CoreTagResolution(
        text=", ".join(tags),
        replacements=tuple(replacements),
        inserted=tuple(inserted),
        verified=tuple(verified),
    )
