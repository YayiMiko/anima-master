from __future__ import annotations

import re

DEFAULT_MAX_CONTENT_TAGS = 80

QUALITY_BLOCKLIST = {
    "masterpiece",
    "best quality",
    "score_7",
    "score_6",
    "score_5",
    "score_4",
    "score_3",
    "score_2",
    "score_1",
    "safe",
    "worst quality",
    "low quality",
    "artist name",
}

CHARACTER_BLOCKLIST = {
    "1 girl",
    "1girl",
    "solo",
}

CHARACTER_IDENTITY_EXACT_BLOCKLIST = {
    "girl",
    "boy",
    "child",
    "teenager",
    "young adult",
    "adult",
    "mature",
    "loli",
    "shota",
    "petite",
    "aged down",
    "age regression",
    "vampire",
    "angel",
    "demon",
    "fox girl",
    "cat girl",
    "animal girl",
    "ahoge",
    "bangs",
    "blunt bangs",
    "sidelocks",
    "hair between eyes",
    "long hair",
    "short hair",
    "medium hair",
    "very long hair",
    "twintails",
    "low twintails",
    "braids",
    "side braid",
    "ponytail",
    "side ponytail",
    "one side up",
    "hair bun",
    "double bun",
    "heterochromia",
    "blue eyes",
    "red eyes",
    "green eyes",
    "pink eyes",
    "purple eyes",
    "yellow eyes",
    "golden eyes",
    "grey eyes",
    "gray eyes",
    "brown eyes",
    "black eyes",
    "black hair",
    "brown hair",
    "blonde hair",
    "white hair",
    "silver hair",
    "blue hair",
    "red hair",
    "pink hair",
    "purple hair",
    "green hair",
    "grey hair",
    "gray hair",
    "fox ears",
    "cat ears",
    "animal ears",
    "pointed ears",
    "tail",
    "fox tail",
    "cat tail",
    "wings",
    "angel wings",
    "demon wings",
    "horns",
    "halo",
    "fang",
    "freckles",
}

CHARACTER_IDENTITY_PATTERNS = (
    re.compile(
        r"\b(?:black|brown|blonde|white|silver|blue|red|pink|purple|green|grey|gray|orange|gold|golden|light|dark|ice blue|silver white)\s+hair\b"
    ),
    re.compile(
        r"\b(?:black|brown|blue|red|pink|purple|green|grey|gray|gold|golden|light|dark|ice blue|amber)\s+eyes?\b"
    ),
    re.compile(
        r"\b(?:hair|bangs|twintails?|braids?|ponytail|sidelocks?|ahoge|hair bun|hair over one eye)\b"
    ),
    re.compile(r"\b(?:ears?|tail|wings?|horns?|halo|fangs?|heterochromia)\b"),
    re.compile(r"\b(?:vampire|angel|demon|fox girl|cat girl|animal girl)\b"),
    re.compile(
        r"\b(?:loli|shota|teenager|young adult|adult|mature|aged down|age regression)\b"
    ),
)

MULTI_CHARACTER_BLOCKLIST = {
    "2girls",
    "3girls",
    "4girls",
    "5girls",
    "6+girls",
    "multiple girls",
    "2boys",
    "3boys",
    "4boys",
    "5boys",
    "6+boys",
    "multiple boys",
    "multiple people",
    "crowd",
    "group",
    "background characters",
    "extra girl",
    "extra person",
    "clone",
    "duplicate",
    "twins",
}

ARTIST_FUNCTION_RE = re.compile(
    r"^artist\s*:\s*(?P<name>[^:=(){}[\]]+?)\s*(?:[:=]\s*[-+]?(?:\d+(?:\.\d+)?|\.\d+)\s*)?$",
    re.I,
)


def split_tags(text: str) -> list[str]:
    """Split mixed LLM output into tag-like fragments."""
    cleaned = str(text or "")
    cleaned = re.sub(r"```.*?```", lambda m: m.group(0).strip("`"), cleaned, flags=re.S)
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


def normalize_tag_key(tag: str) -> str:
    """Normalize a tag for duplicate and blocklist checks."""
    value = str(tag or "").strip().lower()
    if (
        value.startswith("(")
        and value.endswith(")")
        and value.count("(") == 1
        and value.count(")") == 1
    ):
        value = value[1:-1].strip()
    value = re.sub(r":\s*[\d.]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _strip_wrapping_brackets(text: str) -> str:
    value = str(text or "").strip()
    pairs = {"(": ")", "[": "]", "{": "}"}
    changed = True
    while changed and len(value) >= 2:
        changed = False
        left = value[0]
        right = pairs.get(left)
        if right and value.endswith(right):
            value = value[1:-1].strip()
            changed = True
    return value


def normalize_anima_artist_tag(tag: str) -> str:
    """Normalize NAI/WebUI-style artist function tags for Anima.

    Examples:
        `(artist:ningen_mame:0.9)` -> `@ningen mame`
        `artist:ningen_mame` -> `@ningen mame`
    """
    raw = str(tag or "").strip()
    if not raw:
        return ""
    if raw.startswith("@"):
        name = raw[1:].strip().replace("_", " ")
        name = re.sub(r"\s+", " ", name).strip()
        return f"@{name}" if name else raw
    inner = _strip_wrapping_brackets(raw)
    match = ARTIST_FUNCTION_RE.fullmatch(inner)
    if not match:
        return raw
    name = match.group("name").strip()
    if name.startswith("@"):
        name = name[1:].strip()
    name = name.replace("_", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return f"@{name}" if name else raw


def canonical_tag_text(tag: str) -> str:
    """Return the canonical spelling for a few high-impact tags."""
    artist_tag = normalize_anima_artist_tag(tag)
    if artist_tag.startswith("@"):
        return artist_tag
    key = normalize_tag_key(tag)
    if key == "1 girl":
        return "1girl"
    return str(tag or "").strip()


def normalize_artist_tags_text(text: str) -> str:
    """Normalize artist function tags inside a comma-separated tag stream."""
    return join_prompt_parts([str(text or "")])


def is_character_identity_tag(key: str) -> bool:
    """Return whether a tag describes a fixed character's identity/body."""
    compact = normalize_tag_key(key).replace("_", " ")
    if not compact:
        return False
    if compact in CHARACTER_IDENTITY_EXACT_BLOCKLIST:
        return True
    return any(pattern.search(compact) for pattern in CHARACTER_IDENTITY_PATTERNS)


def clean_content_tags(
    text: str,
    max_tags: int = DEFAULT_MAX_CONTENT_TAGS,
    strip_character_tags: bool = True,
    protected_core_tags: tuple[str, ...] = (),
    allow_multi_character: bool = False,
) -> str:
    """Clean LLM-generated content tags before final prompt composition."""
    tags = split_tags(text)
    seen: set[str] = set()
    cleaned: list[str] = []
    artist_re = re.compile(r"^@\S+")
    protected = {normalize_tag_key(tag) for tag in protected_core_tags}
    parenthesized_core_re = re.compile(r"^[a-z0-9_.'-]+_\([a-z0-9_.' -]{2,60}\)$", re.I)
    for tag in tags:
        tag = canonical_tag_text(tag)
        key = normalize_tag_key(tag)
        if not key:
            continue
        if key in seen:
            continue
        if key in QUALITY_BLOCKLIST:
            continue
        if strip_character_tags and key in CHARACTER_BLOCKLIST:
            continue
        if strip_character_tags and is_character_identity_tag(key):
            continue
        if not allow_multi_character and key in MULTI_CHARACTER_BLOCKLIST:
            continue
        if protected and parenthesized_core_re.fullmatch(key) and key not in protected:
            continue
        if artist_re.match(tag.strip()):
            continue
        if len(tag) > 80:
            continue
        seen.add(key)
        cleaned.append(tag)
        if len(cleaned) >= max_tags:
            break
    return ", ".join(cleaned)


def join_prompt_parts(parts: list[str]) -> str:
    """Join prompt fragments while preserving first occurrence order."""
    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for tag in split_tags(part):
            tag = canonical_tag_text(tag)
            key = normalize_tag_key(tag)
            if not key or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
    return ", ".join(tags)
