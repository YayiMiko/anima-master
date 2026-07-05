from dataclasses import dataclass
from typing import Any

try:
    from .prompt_presets import (
        DEFAULT_ARTIST_TAGS,
        DEFAULT_CHARACTER_TAGS,
        DEFAULT_QUALITY_TAGS,
        apply_config_preset,
        active_artist_tags,
        selected_fixed_character,
        strip_raw_prefix,
        wants_default_style,
        wants_sensual_mode,
    )
    from .tag_cleaner import clean_content_tags, join_prompt_parts
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from prompt_presets import (
        DEFAULT_ARTIST_TAGS,
        DEFAULT_CHARACTER_TAGS,
        DEFAULT_QUALITY_TAGS,
        apply_config_preset,
        active_artist_tags,
        selected_fixed_character,
        strip_raw_prefix,
        wants_default_style,
        wants_sensual_mode,
    )
    from tag_cleaner import clean_content_tags, join_prompt_parts


@dataclass(frozen=True)
class PromptBuildResult:
    final_prompt: str
    content_tags: str
    raw_mode: bool
    used_fixed_character: bool
    used_default_style: bool
    required_core_tags: tuple[str, ...] = ()
    character_name: str = ""
    used_sensual_mode: bool = False


def build_final_prompt(
    *,
    user_prompt: str,
    llm_content: str,
    config: dict[str, Any],
    required_core_tags: tuple[str, ...] = (),
) -> PromptBuildResult:
    config = apply_config_preset(config)
    raw_mode, raw_prompt = strip_raw_prefix(user_prompt)
    if raw_mode:
        final = join_prompt_parts([raw_prompt])
        return PromptBuildResult(
            final_prompt=final,
            content_tags=final,
            raw_mode=True,
            used_fixed_character=False,
            used_default_style=False,
            required_core_tags=(),
            character_name="",
            used_sensual_mode=False,
        )

    fixed_character = selected_fixed_character(user_prompt, config)
    use_character = fixed_character is not None
    artist = active_artist_tags(config)
    use_style = wants_default_style(user_prompt, bool(artist.strip()))
    use_sensual = wants_sensual_mode(user_prompt, config)
    quality = str(config.get("quality_prefix") or DEFAULT_QUALITY_TAGS)
    character_name = ""
    if fixed_character is not None:
        character_name, character = fixed_character
    else:
        character = DEFAULT_CHARACTER_TAGS
    if use_character and not character.strip():
        use_character = False
        character_name = ""
    if use_style and not artist.strip():
        use_style = False
    prompt_lower = str(user_prompt or "").lower()
    allow_multi_character = any(
        marker in prompt_lower
        for marker in (
            "2girls",
            "2 girls",
            "3girls",
            "3 girls",
            "multiple girls",
            "multiple people",
            "crowd",
            "group",
            "双人",
            "两人",
            "二人",
            "多人",
            "群像",
            "一群",
        )
    )
    content = clean_content_tags(
        llm_content or user_prompt,
        max_tags=int(config.get("prompt_builder_max_content_tags", 120) or 120),
        strip_character_tags=use_character,
        protected_core_tags=required_core_tags,
        allow_multi_character=allow_multi_character,
        strip_unprotected_character_names=bool(required_core_tags) and not allow_multi_character,
    )
    parts = [quality]
    if required_core_tags:
        parts.append(", ".join(required_core_tags))
    if use_character:
        parts.append(character)
    if use_style:
        parts.append(artist)
    parts.append(content or user_prompt)
    return PromptBuildResult(
        final_prompt=join_prompt_parts(parts),
        content_tags=content,
        raw_mode=False,
        used_fixed_character=use_character,
        used_default_style=use_style,
        required_core_tags=tuple(required_core_tags),
        character_name=character_name,
        used_sensual_mode=use_sensual,
    )
