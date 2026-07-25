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
# Artist preset name. Renamed from "\u5343\u4ee3\u98ce\u683c" to "\u5343\u4ee3base" when the Chiyo
# family gained multiple profiles; the old names stay in the legacy tuple so
# existing configs keep resolving to the current preset.
CHIYO_ARTIST_PRESET_NAME = "\u5343\u4ee3base"
CHIYO_ARTIST_LEGACY_PRESET_NAMES = (
    "\u5343\u4ee3\u98ce\u683c",
    "\u5343\u4ee3\u753b\u98ce",
)

# Chiyo preset profiles. "base" keeps the long-standing behaviour; other
# profiles only declare what they change on top of it.
CHIYO_PROFILE_BASE = "base"
CHIYO_PROFILE_AESTHETIC = "aesthetic"
# Disabled is represented by the empty string so truthiness means "a profile is
# active". Keep this empty, or `_is_chiyo_enabled` would report off as enabled.
CHIYO_PROFILE_OFF = ""
CHIYO_DEFAULT_PROFILE = CHIYO_PROFILE_BASE

# Config values accepted for each profile, so hand-edited configs keep working.
CHIYO_PROFILE_ALIASES: dict[str, str] = {
    "base": CHIYO_PROFILE_BASE,
    "chiyo": CHIYO_PROFILE_BASE,
    "\u5343\u4ee3base": CHIYO_PROFILE_BASE,
    "\u5343\u4ee3\u98ce\u683c": CHIYO_PROFILE_BASE,
    "\u5343\u4ee3\u753b\u98ce": CHIYO_PROFILE_BASE,
    "aesthetic": CHIYO_PROFILE_AESTHETIC,
    "\u5343\u4ee3aesthetic": CHIYO_PROFILE_AESTHETIC,
    "off": CHIYO_PROFILE_OFF,
    "none": CHIYO_PROFILE_OFF,
    "": CHIYO_PROFILE_OFF,
}

# Per-profile config overrides applied by `apply_config_preset`.
#
# `quality_prefix` needs the companion `preset_suppress_quality` flag because
# prompt_builder.py falls back to DEFAULT_QUALITY_TAGS on an empty string.
# `negative_prompt` needs no such flag: the subprocess reads it with
# `config.get("negative_prompt", default)`, which returns the empty string
# when the key is present, so persisting "" is enough to disable it.
CHIYO_PROFILES: dict[str, dict[str, Any]] = {
    CHIYO_PROFILE_BASE: {
        "unet_name": "anima_baseV10.safetensors",
        "cfg": 5.0,
        "preset_suppress_quality": False,
    },
    CHIYO_PROFILE_AESTHETIC: {
        "unet_name": "anima_aestheticV11.safetensors",
        "cfg": 3.0,
        "quality_prefix": "",
        "negative_prompt": "",
        "preset_suppress_quality": True,
    },
}
CHIYO_PROFILE_DISPLAY_NAMES: dict[str, str] = {
    CHIYO_PROFILE_BASE: "\u5343\u4ee3base",
    CHIYO_PROFILE_AESTHETIC: "\u5343\u4ee3aesthetic",
    CHIYO_PROFILE_OFF: "\u672a\u542f\u7528",
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
    profile = resolve_chiyo_profile(result)
    result.pop("chiyo_preset_enabled", None)
    result.pop("preset_profile", None)
    result.pop("preset_suppress_quality", None)
    result["chiyo_preset"] = profile
    if not profile:
        return result

    # Profile overrides win over the incoming config on purpose: keys such as
    # `unet_name` and `cfg` always carry a schema default, so a
    # "keep the user value" merge would make the override dead code.
    for key, value in CHIYO_PROFILES.get(profile, {}).items():
        result[key] = value
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

    profile = resolve_chiyo_profile(current)
    updated["chiyo_preset"] = profile
    updated.pop("chiyo_preset_enabled", None)
    updated.pop("preset_profile", None)
    updated.pop("preset_suppress_quality", None)

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


def resolve_chiyo_profile(config: dict[str, Any]) -> str:
    """Return the selected Chiyo profile id, or an empty string when disabled.

    Accepts the current `chiyo_preset` selector, the legacy
    `chiyo_preset_enabled` boolean, and legacy `preset_profile` aliases so old
    configs keep working after the single-switch design was replaced by a
    multi-profile selector.

    Args:
        config: Plugin configuration mapping.

    Returns:
        A key of `CHIYO_PROFILES` (currently `base` or `aesthetic`), or `""`
        when no Chiyo profile is active.
    """
    selector = str(config.get("chiyo_preset") or "").strip()
    if selector:
        resolved = CHIYO_PROFILE_ALIASES.get(selector.lower())
        if resolved is not None:
            return resolved
        if selector in CHIYO_PROFILE_ALIASES:
            return CHIYO_PROFILE_ALIASES[selector]
        if selector.lower() in CHIYO_PROFILES:
            return selector.lower()
        # Unknown non-empty selector: treat as disabled rather than guessing.
        return ""
    if "chiyo_preset_enabled" in config:
        return CHIYO_DEFAULT_PROFILE if config.get("chiyo_preset_enabled") else ""
    preset = str(config.get("preset_profile") or "").strip()
    if not preset:
        return ""
    return CHIYO_PROFILE_ALIASES.get(
        preset.lower(), CHIYO_PROFILE_ALIASES.get(preset, "")
    )


def chiyo_profile_display_name(config: dict[str, Any]) -> str:
    """Return the human-readable name of the active Chiyo profile.

    Args:
        config: Plugin configuration mapping.

    Returns:
        A display label such as `千代base`, `千代aesthetic`, or `未启用`.
    """
    profile = resolve_chiyo_profile(config)
    return CHIYO_PROFILE_DISPLAY_NAMES.get(
        profile, CHIYO_PROFILE_DISPLAY_NAMES[CHIYO_PROFILE_OFF]
    )


def _is_chiyo_enabled(config: dict[str, Any]) -> bool:
    return bool(resolve_chiyo_profile(config))


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
