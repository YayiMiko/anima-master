from __future__ import annotations

from typing import Any


DEFAULT_QUALITY_TAGS = "masterpiece, best quality, score_7, safe,"
DEFAULT_NEGATIVE_PROMPT = "worst quality, low quality, score_1, score_2, score_3, artist name"
DEFAULT_CHARACTER_TAGS = ""
FIXED_CHARACTER_TAGS: dict[str, str] = {}
DEFAULT_ARTIST_TAGS = ""
CHIYO_PRESET_ALIASES = {"chiyo", "chiyo_preset", "千代", "千代预设", "千代配置"}
CHIYO_STYLE_NAME = "千代画风"
CHIYO_CHARACTER_NAME = "狐莉"
CHIYO_CHARACTER_TAGS = (
    "1 girl, solo, fox girl, (fox ears, inner ear hair), "
    "(white hair, medium hair, hair ornament, hair between eyes), "
    "(heterochromia, ice blue eye and amber eye), fang, black choker,"
)
CHIYO_ARTIST_TAGS = (
    "@yukisiannn, @kani biimu, @ixy, @shnva, "
    "@shiromochi sakura, @stmast,"
)
SENSUAL_MARKERS = (
    "ɬ",
    "色气",
    "涩气",
    "擦边",
    "边界感",
    "性感",
    "诱惑",
    "魅惑",
    "妖艳",
    "撩人",
    "暧昧",
    "挑逗",
    "诱人",
    "透明",
    "透视",
    "黑纱",
    "薄纱",
    "蕾丝",
    "吊带",
    "紧身",
    "露肩",
    "绝对领域",
    "小恶魔",
    "non-r18",
    "non r18",
    "suggestive",
    "seductive",
    "sexy",
    "sensual",
    "alluring",
    "see-through",
    "sheer",
    "transparent",
    "lace",
    "garter",
    "teasing",
)

RAW_PREFIXES = (
    "原样",
    "原样tags",
    "原样tag",
    "原样 tags",
    "原样 tag",
    "直接画",
    "直接出图",
    "直接生图",
    "直接tags",
    "直接tag",
    "直接 tags",
    "直接 tag",
    "不优化",
    "不要优化",
    "跳过优化",
    "跳过提示词优化",
    "raw tags",
    "raw tag",
    "raw",
    "no optimize",
    "no optimization",
    "不用优化",
)

NO_STYLE_MARKERS = (
    "不用我的风格",
    "不要我的风格",
    "不使用我的风格",
    "不要画师词",
    "不用画师词",
    "不加画师词",
    "no artist",
    "no artist tags",
)

NO_CHARACTER_MARKERS = (
    "不要固定角色",
    "不用固定角色",
    "no fixed character",
)


def apply_config_preset(config: dict[str, Any]) -> dict[str, Any]:
    """Return a config copy with an optional user-facing preset applied."""
    result = dict(config or {})
    if _is_chiyo_enabled(result):
        chiyo_enabled = True
    else:
        chiyo_enabled = False
    if not chiyo_enabled:
        return result

    result["chiyo_preset_enabled"] = True
    result["preset_profile"] = "chiyo"
    result["default_style_enabled"] = True

    if not str(result.get("default_style_name") or "").strip():
        result["default_style_name"] = CHIYO_STYLE_NAME
    result["default_artist_tags"] = merge_tag_text(result.get("default_artist_tags"), CHIYO_ARTIST_TAGS)
    fixed_characters = fixed_character_tags(result)
    fixed_characters.setdefault(CHIYO_CHARACTER_NAME, CHIYO_CHARACTER_TAGS)
    result["fixed_characters"] = fixed_characters
    return result


def maybe_materialize_chiyo_preset(config: Any) -> dict[str, Any]:
    """Persist visible Chiyo preset fields back into plugin config when enabled."""
    current = dict(config or {})
    if not _is_chiyo_enabled(current):
        return current

    updated = dict(current)
    updated["default_artist_tags"] = merge_tag_text(
        updated.get("default_artist_tags"),
        CHIYO_ARTIST_TAGS,
    )
    fixed_characters = fixed_character_tags(updated)
    fixed_characters.setdefault(CHIYO_CHARACTER_NAME, CHIYO_CHARACTER_TAGS)
    updated["fixed_characters"] = [
        f"{name}={tags}" for name, tags in fixed_characters.items()
    ]

    if hasattr(config, "save_config") and (
        updated.get("default_artist_tags") != current.get("default_artist_tags")
        or updated.get("fixed_characters") != current.get("fixed_characters")
    ):
        config.save_config(replace_config=updated)
        return dict(config)
    return updated


def merge_tag_text(existing: Any, addition: str) -> str:
    """Merge comma-separated tags while preserving user tags first."""
    tags: list[str] = []
    seen: set[str] = set()
    for source in (existing, addition):
        for tag in str(source or "").split(","):
            text = tag.strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            tags.append(text)
            seen.add(key)
    return ", ".join(tags) + ("," if tags else "")


def _is_chiyo_enabled(config: dict[str, Any]) -> bool:
    if "chiyo_preset_enabled" in config:
        return bool(config.get("chiyo_preset_enabled"))
    preset = str(config.get("preset_profile") or "").strip()
    return preset.lower() in CHIYO_PRESET_ALIASES or preset in CHIYO_PRESET_ALIASES


def fixed_character_tags(config: dict[str, Any]) -> dict[str, str]:
    """Return built-in and user-configured fixed character tags."""
    characters = {name: str(tags) for name, tags in FIXED_CHARACTER_TAGS.items()}
    configured = config.get("fixed_characters")
    if isinstance(configured, dict):
        for name, tags in configured.items():
            name_text = str(name or "").strip()
            tags_text = str(tags or "").strip()
            if name_text and tags_text:
                characters[name_text] = tags_text
    elif isinstance(configured, list):
        for item in configured:
            text = str(item or "").strip()
            if not text:
                continue
            separator = "=" if "=" in text else ":"
            if separator not in text:
                continue
            name, tags = text.split(separator, 1)
            name_text = name.strip()
            tags_text = tags.strip()
            if name_text and tags_text:
                characters[name_text] = tags_text
    return characters


def selected_fixed_character(prompt: str, config: dict[str, Any]) -> tuple[str, str] | None:
    """Return the explicitly requested fixed character, if any."""
    text = str(prompt or "")
    text_lower = text.lower()
    if any(marker.lower() in text_lower for marker in NO_CHARACTER_MARKERS):
        return None

    for name, tags in fixed_character_tags(config).items():
        if name and name in text:
            return name, tags
    return None


def strip_raw_prefix(prompt: str) -> tuple[bool, str]:
    """Strip raw-mode prefixes from a prompt.

    Args:
        prompt: User prompt.

    Returns:
        Pair of raw-mode flag and stripped prompt text.
    """
    text = str(prompt or "").strip()
    lowered = text.lower()
    for prefix in RAW_PREFIXES:
        if lowered.startswith(prefix.lower()):
            return True, text[len(prefix) :].strip(" ，,：:")
    return False, text


def wants_default_style(prompt: str, default: bool = True) -> bool:
    """Return whether default style tags should be applied."""
    text = str(prompt or "").lower()
    if any(marker.lower() in text for marker in NO_STYLE_MARKERS):
        return False
    return default


def wants_sensual_mode(prompt: str, config: dict[str, Any]) -> bool:
    """Return whether prompt should get extra expressive visual language."""
    if not bool(config.get("sensual_mode_enabled", True)):
        return False
    text = str(prompt or "").lower()
    configured = config.get("sensual_mode_markers")
    markers = SENSUAL_MARKERS
    if isinstance(configured, list) and configured:
        markers = tuple(str(item).lower() for item in configured if str(item).strip())
    return any(marker.lower() in text for marker in markers)
