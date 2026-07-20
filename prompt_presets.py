from __future__ import annotations

from typing import Any

DEFAULT_QUALITY_TAGS = "masterpiece, best quality, score_7, safe,"
DEFAULT_NEGATIVE_PROMPT = (
    "worst quality, low quality, score_1, score_2, score_3, artist name"
)
DEFAULT_CHARACTER_TAGS = ""
FIXED_CHARACTER_TAGS: dict[str, str] = {}
DEFAULT_ARTIST_TAGS = ""
LEGACY_HIDDEN_STYLE_KEYS = ("default_style_enabled", "default_style_name")
CHIYO_PRESET_ALIASES = {"chiyo", "chiyo_preset", "千代", "千代预设", "千代配置"}
CHIYO_CHARACTER_NAME = "狐莉"
CHIYO_CHARACTER_TAGS = (
    "1girl, solo, fox girl, (fox ears, inner ear hair), "
    "(white hair, medium hair, hair ornament, hair between eyes), "
    "(heterochromia, ice blue eye and amber eye), fang, black choker,"
)
CHIYO_ARTIST_TAGS = (
    "@yukisiannn, @kani biimu, @ixy, @shnva, @shiromochi sakura, @stmast,"
)
CHIYO_ARTIST_PRESET_NAME = "\u5343\u4ee3\u98ce\u683c"
CHIYO_ARTIST_LEGACY_PRESET_NAMES = ("\u5343\u4ee3\u753b\u98ce",)
STAR_KNIGHT_PRESET_ALIASES = {"star_knight", "闪耀星骑士", "闪耀星骑士预设"}
STAR_KNIGHT_ARTIST_PRESETS = {
    "闪耀星骑士主组": "@kithera, @かんなぎれい, @fuepo,",
    "闪耀星骑士柔光组": "@音棲目るいこ, @天祢るな, @えみゃコーラ,",
    "闪耀星骑士幻想组": "@湯浅彬, @N蔵, @トモセシュンサク,",
}
STAR_KNIGHT_STYLE_PRESETS = {
    "闪耀星骑士基础": "high-end anime game illustration, polished character artwork, clean lineart, crisp contours, clean cel shading, soft gradient shadows, delicate facial features, elegant anime girl, highly detailed costume, sharp silhouette, controlled highlights, glossy material rendering,",
    "闪耀星骑士梦幻偶像": "dreamy fantasy costume, pastel palette, layered frills, lace, flower ornaments, translucent fabric, soft glow, delicate jewelry, sweet elegant girl,",
    "闪耀星骑士暗黑魔法": "dark fantasy costume, black and violet palette, magical ornaments, leather details, thighhighs, glowing runes, elegant sensual design, dramatic color contrast,",
    "闪耀星骑士科技魔女": "fantasy technology, black and gold palette, ornate mechanical accessories, luminous core, hard-surface props, sharp silhouette, polished armor details,",
    "闪耀星骑士东方幻想": "ornate eastern fantasy costume, layered sleeves, decorative knots, floral ornaments, patterned fabric, gold embroidery, flowing fabric, elegant traditional motifs,",
}
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
    "无优化",
    "无优化tags",
    "无优化tag",
    "无优化 tags",
    "无优化 tag",
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
    for key in LEGACY_HIDDEN_STYLE_KEYS:
        result.pop(key, None)
    if _is_star_knight_enabled(result):
        result["star_knight_preset_enabled"] = True
        result["preset_profile"] = "star_knight"
        artists = artist_presets(result)
        for name, tags in STAR_KNIGHT_ARTIST_PRESETS.items():
            artists.setdefault(name, tags)
        result["artist_presets"] = artists
        if not str(result.get("active_artist_preset") or "").strip():
            result["active_artist_preset"] = "闪耀星骑士主组"
        styles = style_presets(result)
        for name, tags in STAR_KNIGHT_STYLE_PRESETS.items():
            styles.setdefault(name, tags)
        result["style_presets"] = styles
        if not str(result.get("active_style_preset") or "").strip():
            result["active_style_preset"] = "闪耀星骑士基础"
    if not _is_chiyo_enabled(result):
        return result

    result["chiyo_preset_enabled"] = True
    result["preset_profile"] = "chiyo"
    result["default_artist_tags"] = merge_tag_text(
        result.get("default_artist_tags"), CHIYO_ARTIST_TAGS
    )
    presets = _normalize_chiyo_artist_presets(artist_presets(result))
    presets.setdefault(CHIYO_ARTIST_PRESET_NAME, CHIYO_ARTIST_TAGS)
    result["artist_presets"] = presets
    active_artist = str(result.get("active_artist_preset") or "").strip()
    if active_artist in CHIYO_ARTIST_LEGACY_PRESET_NAMES:
        result["active_artist_preset"] = CHIYO_ARTIST_PRESET_NAME
    elif not active_artist:
        result["active_artist_preset"] = CHIYO_ARTIST_PRESET_NAME
    fixed_characters = fixed_character_tags(result)
    fixed_characters.setdefault(CHIYO_CHARACTER_NAME, CHIYO_CHARACTER_TAGS)
    result["fixed_characters"] = fixed_characters
    return result


def maybe_materialize_chiyo_preset(
    config: Any,
    *,
    base_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist visible Chiyo preset fields back into plugin config when enabled.

    Args:
        config: Original AstrBot config object or plain dict.
        base_config: Effective config snapshot that should drive this load cycle.

    Returns:
        The normalized visible config used for the current plugin load.
    """
    current = dict(base_config if base_config is not None else config or {})
    persisted = dict(config or {}) if hasattr(config, "save_config") else current
    updated = dict(current)
    for key in LEGACY_HIDDEN_STYLE_KEYS:
        updated.pop(key, None)
    if _is_star_knight_enabled(current):
        updated["star_knight_preset_enabled"] = True
        updated["preset_profile"] = "star_knight"
        artists = artist_presets(updated)
        for name, tags in STAR_KNIGHT_ARTIST_PRESETS.items():
            artists.setdefault(name, tags)
        updated["artist_presets"] = [f"{name}={tags}" for name, tags in artists.items()]
        if not str(updated.get("active_artist_preset") or "").strip():
            updated["active_artist_preset"] = "闪耀星骑士主组"
        styles = style_presets(updated)
        for name, tags in STAR_KNIGHT_STYLE_PRESETS.items():
            styles.setdefault(name, tags)
        updated["style_presets"] = [f"{name}={tags}" for name, tags in styles.items()]
        if not str(updated.get("active_style_preset") or "").strip():
            updated["active_style_preset"] = "闪耀星骑士基础"

    if _is_chiyo_enabled(current):
        updated["default_artist_tags"] = merge_tag_text(
            updated.get("default_artist_tags"),
            CHIYO_ARTIST_TAGS,
        )
        presets = _normalize_chiyo_artist_presets(artist_presets(updated))
        presets.setdefault(CHIYO_ARTIST_PRESET_NAME, CHIYO_ARTIST_TAGS)
        updated["artist_presets"] = [f"{name}={tags}" for name, tags in presets.items()]
        active_artist = str(updated.get("active_artist_preset") or "").strip()
        if active_artist in CHIYO_ARTIST_LEGACY_PRESET_NAMES:
            updated["active_artist_preset"] = CHIYO_ARTIST_PRESET_NAME
        elif not active_artist:
            updated["active_artist_preset"] = CHIYO_ARTIST_PRESET_NAME
        fixed_characters = fixed_character_tags(updated)
        fixed_characters.setdefault(CHIYO_CHARACTER_NAME, CHIYO_CHARACTER_TAGS)
        updated["fixed_characters"] = [
            f"{name}={tags}" for name, tags in fixed_characters.items()
        ]

    if hasattr(config, "save_config") and updated != persisted:
        config.save_config(replace_config=updated)
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


def _is_star_knight_enabled(config: dict[str, Any]) -> bool:
    if "star_knight_preset_enabled" in config:
        return bool(config.get("star_knight_preset_enabled"))
    preset = str(config.get("preset_profile") or "").strip()
    return preset.lower() in STAR_KNIGHT_PRESET_ALIASES or preset in STAR_KNIGHT_PRESET_ALIASES


def _normalize_chiyo_artist_presets(presets: dict[str, str]) -> dict[str, str]:
    """Merge legacy Chiyo artist preset names into the current name."""
    result = dict(presets or {})
    current = result.get(CHIYO_ARTIST_PRESET_NAME, "").strip()
    for legacy_name in CHIYO_ARTIST_LEGACY_PRESET_NAMES:
        legacy = result.pop(legacy_name, "").strip()
        if legacy and not current:
            current = legacy
    if current:
        result[CHIYO_ARTIST_PRESET_NAME] = current
    return result


def artist_presets(config: dict[str, Any]) -> dict[str, str]:
    """Return configured artist tag presets keyed by preset name."""
    presets: dict[str, str] = {}
    configured = config.get("artist_presets")
    if isinstance(configured, dict):
        for name, tags in configured.items():
            name_text = str(name or "").strip()
            tags_text = str(tags or "").strip()
            if name_text and tags_text:
                presets[name_text] = tags_text
    elif isinstance(configured, list):
        for item in configured:
            text = str(item or "").strip()
            if not text:
                continue
            candidates = [
                (text.find(separator), separator)
                for separator in ("=", "＝", "：", ":")
                if separator in text
            ]
            if not candidates:
                continue
            _, separator = min(candidates)
            name, tags = text.split(separator, 1)
            name_text = name.strip()
            tags_text = tags.strip()
            if name_text and tags_text:
                presets[name_text] = tags_text
    return presets


def active_artist_preset_name(config: dict[str, Any]) -> str:
    """Return the configured active artist preset name, if valid."""
    name = str(config.get("active_artist_preset") or "").strip()
    if name and name in artist_presets(config):
        return name
    return ""


def active_artist_tags(config: dict[str, Any]) -> str:
    """Return artist tags currently used for prompt composition."""
    presets = artist_presets(config)
    name = str(config.get("active_artist_preset") or "").strip()
    if name and name in presets:
        return presets[name]
    return str(config.get("default_artist_tags") or DEFAULT_ARTIST_TAGS)


def style_presets(config: dict[str, Any]) -> dict[str, str]:
    """Return configured style tag presets keyed by preset name."""
    presets: dict[str, str] = {}
    configured = config.get("style_presets")
    if isinstance(configured, dict):
        for name, tags in configured.items():
            name_text = str(name or "").strip()
            tags_text = str(tags or "").strip()
            if name_text and tags_text:
                presets[name_text] = tags_text
    elif isinstance(configured, list):
        for item in configured:
            text = str(item or "").strip()
            if not text:
                continue
            candidates = [
                (text.find(separator), separator)
                for separator in ("=", "＝", "：", ":")
                if separator in text
            ]
            if not candidates:
                continue
            _, separator = min(candidates)
            name, tags = text.split(separator, 1)
            name_text = name.strip()
            tags_text = tags.strip()
            if name_text and tags_text:
                presets[name_text] = tags_text
    return presets


def active_style_preset_name(config: dict[str, Any]) -> str:
    """Return the configured active style preset name, if valid."""
    name = str(config.get("active_style_preset") or "").strip()
    if name and name in style_presets(config):
        return name
    return ""


def active_style_tags(config: dict[str, Any]) -> str:
    """Return style tags currently used for prompt composition."""
    presets = style_presets(config)
    name = str(config.get("active_style_preset") or "").strip()
    if name and name in presets:
        return presets[name]
    return str(config.get("style_tags") or "")


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
            candidates = [
                (text.find(separator), separator)
                for separator in ("=", "＝", "：", ":")
                if separator in text
            ]
            if not candidates:
                continue
            _, separator = min(candidates)
            name, tags = text.split(separator, 1)
            name_text = name.strip()
            tags_text = tags.strip()
            if name_text and tags_text:
                characters[name_text] = tags_text
    return characters


def selected_fixed_character(
    prompt: str, config: dict[str, Any]
) -> tuple[str, str] | None:
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


def looks_like_danbooru_tags(text: str) -> bool:
    """Return whether text resembles a comma-separated Danbooru tag stream."""
    values = [part.strip() for part in str(text or "").split(",") if part.strip()]
    if len(values) < 2:
        return False
    return all(" " in value or "_" in value or value.isascii() for value in values)
