from __future__ import annotations

import re


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
    "cute",
    "kawaii",
}

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


def split_tags(text: str) -> list[str]:
    """Split mixed LLM output into tag-like fragments."""
    cleaned = str(text or "")
    cleaned = re.sub(r"```.*?```", lambda m: m.group(0).strip("`"), cleaned, flags=re.S)
    cleaned = cleaned.replace("，", ",").replace("、", ",").replace(";", ",")
    cleaned = cleaned.replace("\n", ",")
    cleaned = re.sub(r"^(?:positive|prompt|tags|提示词|正向提示词)\s*[:：]", "", cleaned.strip(), flags=re.I)
    parts = [part.strip(" \t\r\n,.;:：") for part in cleaned.split(",")]
    return [part for part in parts if part]


def normalize_tag_key(tag: str) -> str:
    """Normalize a tag for duplicate and blocklist checks."""
    value = str(tag or "").strip().lower()
    if value.startswith("(") and value.endswith(")") and value.count("(") == 1 and value.count(")") == 1:
        value = value[1:-1].strip()
    value = re.sub(r":\s*[\d.]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def clean_content_tags(
    text: str,
    max_tags: int = 120,
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
        key = normalize_tag_key(tag)
        if not key:
            continue
        if key in seen:
            continue
        if key in QUALITY_BLOCKLIST:
            continue
        if strip_character_tags and key in CHARACTER_BLOCKLIST:
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
            key = normalize_tag_key(tag)
            if not key or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
    return ", ".join(tags)
