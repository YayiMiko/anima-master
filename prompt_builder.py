from dataclasses import dataclass
from typing import Any

try:
    from .prompt_constraints import PromptConstraintPlan, apply_prompt_constraints
    from .prompt_presets import (
        DEFAULT_CHARACTER_TAGS,
        DEFAULT_QUALITY_TAGS,
        active_artist_tags,
        active_style_tags,
        apply_config_preset,
        selected_fixed_character,
        strip_raw_prefix,
        wants_default_style,
        wants_sensual_mode,
    )
    from .tag_cleaner import (
        DEFAULT_MAX_CONTENT_TAGS,
        clean_content_tags,
        join_prompt_parts,
    )
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from prompt_constraints import PromptConstraintPlan, apply_prompt_constraints
    from prompt_presets import (
        DEFAULT_CHARACTER_TAGS,
        DEFAULT_QUALITY_TAGS,
        active_artist_tags,
        active_style_tags,
        apply_config_preset,
        selected_fixed_character,
        strip_raw_prefix,
        wants_default_style,
        wants_sensual_mode,
    )
    from tag_cleaner import (
        DEFAULT_MAX_CONTENT_TAGS,
        clean_content_tags,
        join_prompt_parts,
    )


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
    constraint_mode: bool = False
    weighted_style_tags: tuple[str, ...] = ()
    constraint_tags: tuple[str, ...] = ()
    removed_constraint_tags: tuple[str, ...] = ()
    constraint_reason: str = ""


def build_final_prompt(
    *,
    user_prompt: str,
    llm_content: str,
    config: dict[str, Any],
    required_core_tags: tuple[str, ...] = (),
    constraint_plan: PromptConstraintPlan | None = None,
    narrative_blocks: tuple[str, ...] = (),
    suppress_fixed_character: bool = False,
    force_multi_character: bool = False,
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

    fixed_character = (
        None
        if suppress_fixed_character
        else selected_fixed_character(user_prompt, config)
    )
    use_character = fixed_character is not None
    artist = active_artist_tags(config)
    style_tags = active_style_tags(config).strip()
    use_style = wants_default_style(user_prompt, bool(artist.strip() or style_tags))
    use_sensual = wants_sensual_mode(user_prompt, config)
    # `preset_suppress_quality` lets a preset ask for no quality prefix at all.
    # Without it an empty `quality_prefix` would fall back to the default tags.
    if config.get("preset_suppress_quality"):
        quality = ""
    else:
        quality = str(config.get("quality_prefix") or DEFAULT_QUALITY_TAGS)
    character_name = ""
    if fixed_character is not None:
        character_name, character = fixed_character
    else:
        character = DEFAULT_CHARACTER_TAGS
    if use_character and not character.strip():
        use_character = False
        character_name = ""
    if use_style and not (artist.strip() or style_tags):
        use_style = False
    prompt_lower = str(user_prompt or "").lower()
    try:
        max_content_tags = int(
            config.get("prompt_builder_max_content_tags", DEFAULT_MAX_CONTENT_TAGS)
        )
    except (TypeError, ValueError):
        max_content_tags = DEFAULT_MAX_CONTENT_TAGS
    if max_content_tags <= 0:
        max_content_tags = DEFAULT_MAX_CONTENT_TAGS
    allow_multi_character = force_multi_character or any(
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
        max_tags=max_content_tags,
        strip_character_tags=use_character,
        protected_core_tags=required_core_tags,
        allow_multi_character=allow_multi_character,
    )
    constraint_result = apply_prompt_constraints(content, constraint_plan)
    content = constraint_result.content_tags
    parts = [quality]
    if required_core_tags:
        parts.append(", ".join(required_core_tags))
    if constraint_result.weighted_style_tags:
        parts.append(", ".join(constraint_result.weighted_style_tags))
    if use_character:
        parts.append(character)
    if use_style:
        if artist.strip():
            parts.append(artist)
        if style_tags:
            parts.append(style_tags)
    parts.append(content or user_prompt)
    final_prompt = join_prompt_parts(parts)
    narrative = tuple(
        str(block or "").strip()
        for block in narrative_blocks
        if str(block or "").strip()
    )
    if narrative:
        final_prompt += "\n\n" + "\n\n".join(narrative)
    return PromptBuildResult(
        final_prompt=final_prompt,
        content_tags=content,
        raw_mode=False,
        used_fixed_character=use_character,
        used_default_style=use_style,
        required_core_tags=tuple(required_core_tags),
        character_name=character_name,
        used_sensual_mode=use_sensual,
        constraint_mode=constraint_result.triggered,
        weighted_style_tags=constraint_result.weighted_style_tags,
        constraint_tags=constraint_result.priority_tags,
        removed_constraint_tags=constraint_result.removed_tags,
        constraint_reason=constraint_result.reason,
    )
