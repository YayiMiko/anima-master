from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from .danbooru_resolver import DanbooruResolver
    from .multi_person_prompt import (
        build_multi_person_plan_prompt,
        parse_multi_person_plan,
        render_multi_person_character,
    )
    from .outfit_transfer import (
        build_outfit_summary_prompt,
        build_outfit_transfer_block,
        detect_outfit_transfer,
        extract_reference_tag_text,
        filter_outfit_tags,
        preferred_search_prompt,
    )
    from .prompt_background import (
        DEFAULT_PORTRAIT,
        extract_background_mode,
    )
    from .prompt_builder import (
        build_final_prompt,
    )
    from .prompt_constraints import (
        build_constraint_plan_prompt,
        parse_constraint_plan,
    )
    from .prompt_presets import (
        apply_config_preset,
        fixed_character_tags,
        selected_fixed_character,
        strip_raw_prefix,
        wants_sensual_mode,
    )
    from .prompt_research import PromptResearcher
    from .prompt_templates import build_llm_prompt
    from .tag_cleaner import split_tags
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from danbooru_resolver import DanbooruResolver
    from multi_person_prompt import (
        build_multi_person_plan_prompt,
        parse_multi_person_plan,
        render_multi_person_character,
    )
    from outfit_transfer import (
        build_outfit_summary_prompt,
        build_outfit_transfer_block,
        detect_outfit_transfer,
        extract_reference_tag_text,
        filter_outfit_tags,
        preferred_search_prompt,
    )
    from prompt_background import (
        DEFAULT_PORTRAIT,
        extract_background_mode,
    )
    from prompt_builder import (
        build_final_prompt,
    )
    from prompt_constraints import (
        build_constraint_plan_prompt,
        parse_constraint_plan,
    )
    from prompt_presets import (
        apply_config_preset,
        fixed_character_tags,
        selected_fixed_character,
        strip_raw_prefix,
        wants_sensual_mode,
    )
    from prompt_research import PromptResearcher
    from prompt_templates import build_llm_prompt
    from tag_cleaner import split_tags


@dataclass(frozen=True)
class PromptPipelineResult:
    """Prompt pipeline output and debug summary.

    Args:
        final_prompt: Prompt sent to the ComfyUI tool.
        summary: Non-secret prompt build summary for logs and last_task.json.
    """

    final_prompt: str
    summary: dict[str, Any]


class PromptPipeline:
    """Build Anima prompts from chat text while keeping plugin main thin."""

    def __init__(
        self,
        *,
        context: Any,
        config: dict[str, Any],
        logger: Any,
        danbooru_resolver: DanbooruResolver,
        researcher: PromptResearcher,
        get_bool: Callable[[str, bool], bool],
        get_int: Callable[[str, int], int],
        get_float: Callable[[str, float], float],
        get_str: Callable[[str, str], str],
        shorten: Callable[[str, int], str],
    ):
        """Store dependencies supplied by the AstrBot plugin.

        Args:
            context: AstrBot plugin context used for provider lookup and LLM calls.
            config: Plugin configuration dict.
            logger: Logger compatible with AstrBot logger methods.
            danbooru_resolver: Danbooru core tag resolver.
            researcher: Optional web/deep-thinking research planner.
            get_bool: Config boolean accessor.
            get_int: Config integer accessor.
            get_float: Config float accessor.
            get_str: Config string accessor.
            shorten: Text-shortening helper for summaries.
        """
        self.context = context
        self.config = config
        self.logger = logger
        self._danbooru_resolver = danbooru_resolver
        self._researcher = researcher
        self._bool = get_bool
        self._int = get_int
        self._float = get_float
        self._str = get_str
        self._shorten = shorten

    async def _current_chat_provider_id(self, event: Any) -> str:
        configured = self._str("prompt_builder_provider_id", "").strip()
        if configured:
            return configured
        try:
            provider_id = await self.context.get_current_chat_provider_id(
                event.unified_msg_origin
            )
            return str(provider_id or "").strip()
        except Exception as exc:
            self.logger.warning(
                "[comfyui_agent] failed to get current chat provider: %s", exc
            )
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        return str(
            cfg.get("provider_settings", {}).get("default_provider_id") or ""
        ).strip()

    async def _generate_prompt_tags_with_llm(
        self,
        *,
        provider_id: str,
        llm_prompt: str,
        use_deep_thinking: bool,
        fixed_character: bool,
        character_name: str = "",
    ) -> str:
        if character_name:
            character_rule = f"不要输出固定角色“{character_name}”的固有外观设定。"
        else:
            character_rule = (
                "用户没有使用固定角色时，如果用户明确点名现有作品角色，"
                "第一项必须输出最可信的标准 Danbooru 角色 tag，使用罗马字和下划线，必要时带作品消歧括号；"
                "禁止省略角色 tag 而只写外观，后续程序会联网查询 character 分类并校正。"
                "之后可以并且应该输出主体所需的固有外观设定。"
            )
        creative_rule = (
            "默认采用自由创作策略：在保留用户明确要求和角色身份的前提下，"
            "可以主动发展统一主题并补充有助于最终画面表现的可见内容，但不得在用户未提背景时创造场景；"
            "以协调、精致和好看为优先，不机械追求固定tag数量。"
        )
        kwargs: dict[str, Any] = {
            "chat_provider_id": provider_id,
            "prompt": llm_prompt,
            "system_prompt": (
                "你是 Anima 模型的 Danbooru tag 提示词助手。"
                "请在内部充分推理和校验参考对象的视觉特征，但不要输出思考过程。"
                "只输出英文 danbooru tags，用英文逗号分隔。"
                "不要解释，不要 Markdown，不要输出质量词或画师词。"
                "严格按用户原始文字判断背景；未提背景时使用白底立绘。"
                "按用户是否明确要求场景，在最后输出且只输出一个背景控制标记。"
                f"{character_rule}"
                f"{creative_rule}"
            ),
            "max_tokens": self._int("prompt_builder_max_tokens", 700),
        }
        if use_deep_thinking:
            kwargs["reasoning_effort"] = (
                self._str("prompt_builder_reasoning_effort", "high") or "high"
            )
            kwargs["thinking"] = {"type": "enabled"}
        response = await self.context.llm_generate(**kwargs)
        return str(getattr(response, "completion_text", "") or "").strip()

    async def _generate_outfit_summary_with_llm(
        self,
        *,
        provider_id: str,
        summary_prompt: str,
        use_deep_thinking: bool,
    ) -> str:
        kwargs: dict[str, Any] = {
            "chat_provider_id": provider_id,
            "prompt": summary_prompt,
            "system_prompt": (
                "你是二次元服装解析助手。"
                "请在内部充分推理来源服装结构，但不要输出思考过程。"
                "只输出英文 danbooru tags，用英文逗号分隔。"
                "不要解释，不要 Markdown，不要输出质量词、画师词或角色身份词。"
            ),
            "max_tokens": min(self._int("prompt_builder_max_tokens", 700), 500),
        }
        if use_deep_thinking:
            kwargs["reasoning_effort"] = (
                self._str("prompt_builder_reasoning_effort", "high") or "high"
            )
            kwargs["thinking"] = {"type": "enabled"}
        response = await self.context.llm_generate(**kwargs)
        return str(getattr(response, "completion_text", "") or "").strip()

    async def _generate_character_candidates_with_llm(
        self,
        *,
        provider_id: str,
        user_prompt: str,
        rejected_content: str,
        target_name: str = "",
    ) -> tuple[str, ...]:
        """Extract bounded Danbooru character candidates from the user request.

        Args:
            provider_id: Active AstrBot provider identifier.
            user_prompt: Original request containing the named character.
            rejected_content: Initial LLM tags that online lookup could not verify.
            target_name: Optional character name selected by a multi-person plan.

        Returns:
            Normalized candidate tags proposed for evidence-based lookup.
        """
        response = await self.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=(
                "Extract the explicitly named existing anime/game character from "
                "the user request and propose up to 6 possible canonical Danbooru "
                "character tags. Preserve the exact source-language name and infer "
                "the work/copyright separately. Candidate tags must use lowercase "
                "ASCII, underscores, and a work disambiguation suffix when known.\n\n"
                'Return JSON only: {"source_name":"原文中的名字",'
                '"copyright":"work name","tag_candidates":["name_(work)"]}.\n'
                "The source_name must be an exact substring of the user request. "
                "Do not invent a character when none is explicitly named.\n\n"
                f"Target name: {target_name or 'not separately specified'}\n"
                f"User request: {user_prompt}\n"
                f"Initial character tags to cross-check: "
                f"{self._shorten(rejected_content, 500)}"
            ),
            system_prompt=(
                "You resolve named anime and game characters to candidate Danbooru "
                "tags. Return valid JSON only. Your candidates are search hints, "
                "not authoritative answers."
            ),
            max_tokens=350,
        )
        raw = str(getattr(response, "completion_text", "") or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            raw = match.group(0)
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return ()
        if not isinstance(data, dict):
            return ()
        source_name = str(data.get("source_name") or "").strip()
        if not source_name or source_name not in user_prompt:
            return ()
        raw_candidates = data.get("tag_candidates")
        if not isinstance(raw_candidates, list):
            return ()
        candidates: list[str] = []
        for item in raw_candidates:
            candidate = str(item or "").strip().lower()
            candidate = re.sub(r"\s+", "_", candidate)
            if not re.fullmatch(r"[a-z0-9_.'():-]{3,100}", candidate):
                continue
            if candidate not in candidates:
                candidates.append(candidate)
        return tuple(candidates[:6])

    async def _generate_constraint_plan_with_llm(
        self,
        *,
        provider_id: str,
        plan_prompt: str,
    ) -> str:
        """Ask the active provider for a low-CFG constraint plan.

        Args:
            provider_id: AstrBot provider identifier.
            plan_prompt: Structured constraint planning prompt.

        Returns:
            Raw JSON text returned by the provider.
        """
        response = await self.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=plan_prompt,
            system_prompt=(
                "You are a strict JSON planner for anime image prompt constraints. "
                "Return only valid JSON. Do not output Markdown or explanations."
            ),
            max_tokens=450,
        )
        return str(getattr(response, "completion_text", "") or "").strip()

    async def _generate_multi_person_plan_with_llm(
        self,
        *,
        provider_id: str,
        plan_prompt: str,
        use_deep_thinking: bool,
    ) -> str:
        """Ask the active provider for a structured multi-person scene plan.

        Args:
            provider_id: AstrBot provider identifier.
            plan_prompt: Structured planning request.
            use_deep_thinking: Whether to request provider reasoning support.

        Returns:
            Raw JSON text returned by the provider.
        """
        kwargs: dict[str, Any] = {
            "chat_provider_id": provider_id,
            "prompt": plan_prompt,
            "system_prompt": (
                "You plan multi-character Anima illustrations. "
                "Return only valid JSON matching the requested schema. "
                "Keep every character's identity and attributes in its own block."
            ),
            "max_tokens": min(self._int("prompt_builder_max_tokens", 700), 900),
        }
        if use_deep_thinking:
            kwargs["reasoning_effort"] = (
                self._str("prompt_builder_reasoning_effort", "high") or "high"
            )
            kwargs["thinking"] = {"type": "enabled"}
        response = await self.context.llm_generate(**kwargs)
        return str(getattr(response, "completion_text", "") or "").strip()

    async def _build_multi_person_prompt(
        self,
        *,
        provider_id: str,
        prompt: str,
        prompt_config: dict[str, Any],
        use_deep_thinking: bool,
        summary: dict[str, Any],
        original_user_prompt: str = "",
    ) -> PromptPipelineResult | None:
        """Build a hybrid tag and natural-language prompt for 2–4 people.

        Args:
            provider_id: Active chat provider identifier.
            prompt: User's multi-person scene request.
            prompt_config: Effective preset-aware plugin configuration.
            use_deep_thinking: Whether the provider should use reasoning mode.
            summary: Mutable request summary populated by this branch.
            original_user_prompt: User text before reference-context expansion.

        Returns:
            Completed prompt result, or None when planning fails and generation
            must stop without entering the ordinary prompt path.
        """
        configured_characters = fixed_character_tags(prompt_config)
        mentioned_fixed_characters = {
            name: tags
            for name, tags in configured_characters.items()
            if name and name in prompt
        }
        plan_prompt = build_multi_person_plan_prompt(
            prompt,
            fixed_characters=mentioned_fixed_characters,
            original_user_prompt=original_user_prompt,
        )
        raw_plan = ""
        plan = None
        planner_error = "invalid_plan"
        planner_retry_count = 0
        for attempt in range(2):
            try:
                raw_plan = await self._generate_multi_person_plan_with_llm(
                    provider_id=provider_id,
                    plan_prompt=plan_prompt,
                    use_deep_thinking=use_deep_thinking,
                )
            except Exception as exc:
                planner_error = self._shorten(str(exc), 300)
                self.logger.warning(
                    "[comfyui_agent] multi-person planner attempt %s failed: %s",
                    attempt + 1,
                    exc,
                )
            else:
                candidate = parse_multi_person_plan(raw_plan)
                if candidate is not None:
                    allowed_aliases = {
                        f"CHARACTER {letter}"
                        for letter in "ABCD"[: len(candidate.characters)]
                    }
                    interaction_aliases = {
                        alias.upper()
                        for interaction in candidate.interactions
                        for alias in re.findall(
                            r"\bCharacter\s+[A-D]\b",
                            interaction,
                            flags=re.IGNORECASE,
                        )
                    }
                    if (
                        candidate.interactions
                        and interaction_aliases
                        and not interaction_aliases.issubset(allowed_aliases)
                    ):
                        planner_error = "invalid_interaction_aliases"
                    else:
                        plan = candidate
                        break
                else:
                    planner_error = "invalid_plan"
            if attempt == 0:
                planner_retry_count = 1
                plan_prompt += (
                    "\nThe previous response was invalid. Return corrected JSON only. "
                    "Keep 2 to 4 characters, reference only defined Character aliases "
                    "inside interactions, and preserve one coherent shared scene."
                )
        if plan is None:
            self.logger.warning(
                "[comfyui_agent] multi-person planner stopped: %s", planner_error
            )
            summary.update(
                {
                    "multi_person_mode": True,
                    "multi_person_plan_failed": True,
                    "multi_person_error": planner_error,
                    "multi_person_planner_retry_count": planner_retry_count,
                }
            )
            return None

        character_blocks: list[str] = []
        character_entity_names: list[set[str]] = []
        resolved_count = 0
        fixed_character_count = 0
        danbooru_resolved_count = 0
        unresolved_character_count = 0
        character_resolution_statuses: list[dict[str, Any]] = []
        character_slots: list[str] = []
        character_roles: list[str] = []
        emphasized_anchor_count = 0
        used_fixed_names: set[str] = set()
        fixed_genders: list[str] = []
        aliases = ("Character A", "Character B", "Character C", "Character D")
        explicit_position_requested = bool(
            re.search(
                r"左边|右边|左侧|右侧|前景|后方|前后站位|"
                r"\bon\s+the\s+(?:left|right)\b|\bforeground\b|\bbackground\b",
                prompt,
                flags=re.IGNORECASE,
            )
        )
        spatial_mode = plan.spatial_mode
        if explicit_position_requested:
            spatial_mode = "explicit_positions"
        elif plan.interactions:
            spatial_mode = "shared_contact"
        elif spatial_mode == "explicit_positions":
            spatial_mode = "shared_scene"
        grouped_contact = spatial_mode == "shared_contact"
        for index, character in enumerate(plan.characters):
            character_slots.append(character.slot)
            fixed_name = next(
                (
                    name
                    for name in mentioned_fixed_characters
                    if name not in used_fixed_names
                    and (
                        name == character.name
                        or name in character.name
                        or character.name in name
                    )
                ),
                "",
            )
            fixed_tags = ""
            resolved_identity = ""
            resolution_status = "not_requested"
            candidate_hints: tuple[str, ...] = ()
            if fixed_name:
                used_fixed_names.add(fixed_name)
                configured_tags = split_tags(configured_characters[fixed_name])
                normalized_configured_tags = {
                    tag.lower().replace(" ", "") for tag in configured_tags
                }
                if "1girl" in normalized_configured_tags:
                    fixed_genders.append("girl")
                elif "1boy" in normalized_configured_tags:
                    fixed_genders.append("boy")
                fixed_tags = ", ".join(
                    tag
                    for tag in configured_tags
                    if tag.lower()
                    not in {
                        "1girl",
                        "1 girl",
                        "1boy",
                        "1 boy",
                        "solo",
                    }
                )
                resolved_count += 1
                fixed_character_count += 1
                resolution_status = "fixed"
            elif character.danbooru_candidate:
                resolution = await self._danbooru_resolver.resolve_detailed(
                    llm_content=character.danbooru_candidate,
                    user_prompt=character.name or prompt,
                    fixed_character=False,
                )
                if resolution.status == "unresolved" or resolution.explicit_request:
                    try:
                        candidate_hints = (
                            await self._generate_character_candidates_with_llm(
                                provider_id=provider_id,
                                user_prompt=prompt,
                                rejected_content=character.danbooru_candidate,
                                target_name=character.name,
                            )
                        )
                    except Exception as exc:
                        self.logger.warning(
                            "[comfyui_agent] multi-person character candidate "
                            "planner failed for %s: %s",
                            character.name or character.danbooru_candidate,
                            exc,
                        )
                    if candidate_hints:
                        resolution = await self._danbooru_resolver.resolve_detailed(
                            llm_content=character.danbooru_candidate,
                            user_prompt=character.name or prompt,
                            fixed_character=False,
                            candidate_hints=candidate_hints,
                        )
                resolution_status = resolution.status
                if resolution.status == "resolved":
                    resolved_identity = resolution.canonical_tag or next(
                        iter(split_tags(resolution.text)), ""
                    )
                    if len(resolution.identity_tags) > 1:
                        fixed_tags = ", ".join(resolution.identity_tags[1:])
                    resolved_count += 1
                    danbooru_resolved_count += 1
                else:
                    resolved_identity = character.danbooru_candidate
                    unresolved_character_count += 1
            available_identity_tags = [
                tag.strip(" ()")
                for tag in split_tags(fixed_tags or character.appearance)
                if tag.strip(" ()")
                and tag.strip(" ()").lower()
                not in {"1girl", "1 girl", "1boy", "1 boy", "solo"}
            ]
            proposed_identity_tags = [
                str(tag).strip(" ()")
                for tag in character.identity_anchors
                if str(tag).strip(" ()")
            ]
            if fixed_name or resolution_status == "resolved":
                fixed_source = re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    (
                        configured_characters[fixed_name] if fixed_name else fixed_tags
                    ).lower(),
                )
                identity_tags = [
                    tag
                    for tag in proposed_identity_tags
                    if re.sub(r"[^a-z0-9]+", " ", tag.lower()).strip() in fixed_source
                ][:6]
            else:
                identity_tags = proposed_identity_tags[:6]
            if not identity_tags:
                identity_tags = available_identity_tags[:6]
            visual_label = str(character.visual_label or "").strip().lower()
            if visual_label and (fixed_name or resolution_status == "resolved"):
                label_terms = re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    visual_label.replace("haired", "hair")
                    .replace("eyed", "eyes")
                    .replace("eared", "ears"),
                ).split()
                label_terms = [
                    term
                    for term in label_terms
                    if term not in {"girl", "boy", "woman", "man", "person"}
                ]
                label_source = re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    (
                        configured_characters[fixed_name] if fixed_name else fixed_tags
                    ).lower(),
                )
                if not label_terms or any(
                    term not in label_source for term in label_terms
                ):
                    visual_label = ""
            if not visual_label or re.search(
                r"\b(?:character\s+[a-d]|first|second|third|fourth|rider|"
                r"support(?:ing|er)?|left|right|top|bottom)\b",
                visual_label,
                flags=re.IGNORECASE,
            ):
                descriptors: list[str] = []
                for tag in identity_tags[:2]:
                    descriptor = re.sub(r"[()_:]+", " ", tag.lower())
                    descriptor = re.sub(r"\s+", " ", descriptor).strip()
                    descriptor = re.sub(r"\s+hair$", "-haired", descriptor)
                    descriptor = re.sub(r"\s+eyes$", "-eyed", descriptor)
                    descriptor = re.sub(r"\s+ears$", "-eared", descriptor)
                    if descriptor:
                        descriptors.append(descriptor.replace(" ", "-"))
                gender_label = (
                    "girl"
                    if any("girl" in tag.lower() for tag in plan.count_tags)
                    else "person"
                )
                visual_label = " ".join((*descriptors, gender_label)).strip()
            if not visual_label:
                visual_label = str(character.role or aliases[index]).strip().lower()
            if visual_label in character_roles:
                visual_label = f"{visual_label} {index + 1}"
            character_roles.append(visual_label)

            emphasized = {
                re.sub(r"[^a-z0-9]+", " ", str(tag).lower()).strip()
                for tag in character.emphasized_anchors
                if str(tag).strip()
            }
            rendered_identity_tags = [
                f"({tag}:1.3)"
                if re.sub(r"[^a-z0-9]+", " ", tag.lower()).strip() in emphasized
                else tag
                for tag in identity_tags
            ]
            emphasized_anchor_count += sum(
                rendered != original
                for rendered, original in zip(
                    rendered_identity_tags, identity_tags, strict=True
                )
            )
            character_resolution_statuses.append(
                {
                    "alias": aliases[index],
                    "role": visual_label,
                    "name": character.name,
                    "status": resolution_status,
                    "canonical_tag": resolved_identity
                    if resolution_status == "resolved"
                    else "",
                    "identity_tags": identity_tags,
                    "emphasized_identity_tags": [
                        tag
                        for tag in identity_tags
                        if re.sub(r"[^a-z0-9]+", " ", tag.lower()).strip() in emphasized
                    ],
                    "candidate_hints": list(candidate_hints),
                }
            )
            character_entity_names.append(
                {
                    value
                    for value in (
                        character.name,
                        character.danbooru_candidate,
                        fixed_name,
                        resolved_identity,
                    )
                    if value
                }
            )
            character_blocks.append(
                render_multi_person_character(
                    character,
                    alias=visual_label,
                    resolved_identity=resolved_identity,
                    fixed_tags=fixed_tags if fixed_name else "",
                    grouped_contact=grouped_contact,
                    explicit_positions=spatial_mode == "explicit_positions",
                    identity_anchors=tuple(rendered_identity_tags),
                    include_pose=not grouped_contact,
                )
            )

        blocked_positive_markers = (
            "split screen",
            "panel",
            "multiple view",
            "alternate view",
            "character sheet",
            "duplicate character",
            "cloned character",
        )
        character_count = len(plan.characters)
        deterministic_count_tags: tuple[str, ...] = ()
        if len(fixed_genders) == character_count:
            girl_count = fixed_genders.count("girl")
            boy_count = fixed_genders.count("boy")
            deterministic_count_tags = tuple(
                tag
                for tag in (
                    f"{girl_count}girls" if girl_count else "",
                    f"{boy_count}boys" if boy_count else "",
                )
                if tag
            )
        if not deterministic_count_tags:
            deterministic_count_tags = tuple(
                tag
                for tag in plan.count_tags
                if (
                    (
                        match := re.fullmatch(
                            r"\s*(\d+)\s*(girls?|boys?|people|persons?)\s*",
                            tag,
                            flags=re.IGNORECASE,
                        )
                    )
                    and int(match.group(1)) == character_count
                )
            )[:1] or (f"{character_count}people",)
        filtered_common_tags = tuple(
            tag
            for tag in plan.common_tags
            if not any(marker in tag.lower() for marker in blocked_positive_markers)
            and tag.strip().lower() != str(plan.relationship_tag or "").strip().lower()
            and not re.fullmatch(
                r"\s*\d+\s*(girls?|boys?|people|persons?)\s*",
                tag,
                flags=re.IGNORECASE,
            )
        )
        if plan.background_mode == DEFAULT_PORTRAIT:
            filtered_common_tags = tuple(
                dict.fromkeys(
                    (
                        *filtered_common_tags,
                        "full body",
                        "centered",
                        "simple background",
                        "white background",
                    )
                )
            )
        relationship_tag = str(plan.relationship_tag or "").strip()
        common_content = ", ".join(
            (
                *deterministic_count_tags,
                *(("duo",) if character_count == 2 else ()),
                *((relationship_tag,) if relationship_tag else ()),
                *filtered_common_tags,
            )
        )
        low_cfg_harness = bool(prompt_config.get("low_cfg_harness_enabled", False))
        constraint_raw = ""
        constraint_plan = parse_constraint_plan("")
        if low_cfg_harness:
            try:
                constraint_raw = await self._generate_constraint_plan_with_llm(
                    provider_id=provider_id,
                    plan_prompt=build_constraint_plan_prompt(
                        user_prompt=prompt,
                        llm_content=common_content,
                    ),
                )
                constraint_plan = parse_constraint_plan(constraint_raw)
            except Exception as exc:
                self.logger.warning(
                    "[comfyui_agent] multi-person constraint planner failed: %s",
                    exc,
                )

        normalized_interactions: list[str] = []
        for interaction in plan.interactions:
            normalized = interaction
            replacements = sorted(
                (
                    (name, aliases[index])
                    for index, names in enumerate(character_entity_names)
                    for name in names
                    if name.lower() != aliases[index].lower()
                ),
                key=lambda item: len(item[0]),
                reverse=True,
            )
            for name, alias in replacements:
                if any(ord(char) > 127 for char in name):
                    normalized = normalized.replace(name, f" {alias} ")
                else:
                    normalized = re.sub(
                        rf"(?<![\w]){re.escape(name)}(?![\w])",
                        alias,
                        normalized,
                        flags=re.IGNORECASE,
                    )
            normalized = re.sub(r"\s+", " ", normalized).strip()
            normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
            normalized_interactions.append(normalized)

        normalized_aliases = {
            alias.upper()
            for interaction in normalized_interactions
            for alias in re.findall(
                r"\bCharacter\s+[A-D]\b",
                interaction,
                flags=re.IGNORECASE,
            )
        }
        allowed_aliases = {alias.upper() for alias in aliases[: len(plan.characters)]}
        if normalized_interactions and (
            not normalized_aliases.issubset(allowed_aliases)
            or len(normalized_aliases) < 2
        ):
            summary.update(
                {
                    "multi_person_mode": True,
                    "multi_person_plan_failed": True,
                    "multi_person_error": "invalid_interaction_aliases",
                    "multi_person_planner_retry_count": planner_retry_count,
                }
            )
            return None

        display_interactions: list[str] = []
        for interaction in normalized_interactions:
            displayed = interaction
            for alias, role in zip(
                aliases[: len(plan.characters)], character_roles, strict=True
            ):
                displayed = re.sub(
                    rf"\b{re.escape(alias)}\b",
                    f"the {role}",
                    displayed,
                    flags=re.IGNORECASE,
                )
            display_interactions.append(displayed)

        scene_guard = "The composition shows one shared continuous moment."
        relative_position = ""
        if spatial_mode == "explicit_positions" and len(plan.characters) == 2:
            slot_aliases = {
                character.slot: f"the {character_roles[index]}"
                for index, character in enumerate(plan.characters)
            }
            if {"left", "right"}.issubset(slot_aliases):
                relative_position = (
                    f"{slot_aliases['left']} stands immediately beside "
                    f"{slot_aliases['right']}, to {slot_aliases['right']}'s left, "
                    "while both remain in the same central group."
                )
            elif {"foreground", "background"}.issubset(slot_aliases):
                relative_position = (
                    f"{slot_aliases['foreground']} stands slightly in front of "
                    f"{slot_aliases['background']} while both remain together in "
                    "the same continuous scene."
                )
        narrative_blocks = tuple(
            block
            for block in (
                *character_blocks,
                *display_interactions,
                relative_position,
                scene_guard,
            )
            if block
        )
        built = build_final_prompt(
            user_prompt=prompt,
            llm_content=common_content,
            config=prompt_config,
            constraint_plan=constraint_plan,
            narrative_blocks=narrative_blocks,
            suppress_fixed_character=True,
            force_multi_character=True,
        )
        content_tag_count = len(split_tags(built.content_tags))
        summary.update(
            {
                "multi_person_mode": True,
                "multi_person_plan_failed": False,
                "multi_person_planner_retry_count": planner_retry_count,
                "planned_character_count": len(plan.characters),
                "resolved_character_count": resolved_count,
                "fixed_character_count": fixed_character_count,
                "danbooru_resolved_count": danbooru_resolved_count,
                "unresolved_character_count": unresolved_character_count,
                "character_resolution_statuses": character_resolution_statuses,
                "named_character_detected": bool(plan.characters),
                "character_slots": character_slots,
                "character_roles": character_roles,
                "interaction_count": len(plan.interactions),
                "relationship_tag": relationship_tag,
                "emphasized_anchor_count": emphasized_anchor_count,
                "grouped_contact": grouped_contact,
                "spatial_mode": spatial_mode,
                "background_mode": plan.background_mode,
                "explicit_position_requested": explicit_position_requested,
                "interaction_aliases_normalized": (
                    tuple(normalized_interactions) != plan.interactions
                ),
                "composition_source": "deterministic",
                "hybrid_prompt": True,
                "raw_mode": False,
                "deep_thinking": use_deep_thinking,
                "fixed_character": bool(used_fixed_names),
                "fixed_character_name": ", ".join(sorted(used_fixed_names)),
                "sensual_mode": wants_sensual_mode(prompt, prompt_config),
                "default_style": built.used_default_style,
                "low_cfg_harness": low_cfg_harness,
                "constraint_mode": built.constraint_mode,
                "weighted_style_tags": list(built.weighted_style_tags),
                "constraint_tags": list(built.constraint_tags),
                "removed_constraint_tags": list(built.removed_constraint_tags),
                "constraint_reason": built.constraint_reason,
                "llm_failed": False,
                "llm_error": "",
                "llm_content_tag_count": content_tag_count,
                "removed_content_tag_count": max(
                    0,
                    len(split_tags(common_content)) - content_tag_count,
                ),
                "llm_content_chars": len(built.content_tags),
                "final_prompt_chars": len(built.final_prompt),
                "final_prompt_head": self._shorten(built.final_prompt, 600),
            }
        )
        if self._bool("debug_prompt_enabled", False):
            summary.update(
                {
                    "multi_person_plan_prompt": plan_prompt,
                    "multi_person_plan": raw_plan,
                    "constraint_plan": constraint_raw,
                    "final_prompt": built.final_prompt,
                }
            )
        return PromptPipelineResult(built.final_prompt, summary)

    async def build(
        self,
        event: Any,
        user_prompt: str,
        mode: str = "txt2img",
        *,
        multi_person: bool = False,
        original_user_prompt: str = "",
    ) -> PromptPipelineResult:
        """Build the final prompt and summary for one generation request.

        Args:
            event: AstrBot message event for provider and per-chat config lookup.
            user_prompt: User prompt after reference-image augmentation.
            mode: Generation mode, such as `txt2img` or `img2img`.
            multi_person: Whether `/anm 多人` requested structured planning.
            original_user_prompt: User text before reference-context augmentation.

        Returns:
            Final prompt plus a serializable summary dict.
        """
        original_prompt = str(user_prompt or "").strip()
        background_intent_prompt = str(original_user_prompt or original_prompt).strip()
        legacy_creative_flag_re = re.compile(
            r"(?<!\S)--(?:自由发挥|自由拓展|创意拓展|创意扩展|creative)"
            r"(?=$|\s|[,，;；:：])",
            re.IGNORECASE,
        )
        prompt = legacy_creative_flag_re.sub(" ", original_prompt).strip()
        prompt = re.sub(r"^[\s,，;；:：]+|[\s,，;；:：]+$", "", prompt)
        prompt = re.sub(r"([,，;；])\s*[,，;；]+", r"\1", prompt)
        prompt = re.sub(r"\s+", " ", prompt)
        summary: dict[str, Any] = {
            "prompt_optimize_enabled": self._bool("prompt_optimize_enabled", True),
            "mode": mode,
            "multi_person_mode": bool(multi_person),
            "original_prompt_head": self._shorten(original_prompt, 600),
        }
        if not self._bool("prompt_optimize_enabled", True):
            summary.update(
                {
                    "skipped_reason": "prompt_optimize_disabled",
                    "final_prompt_head": self._shorten(prompt, 600),
                    "final_prompt_chars": len(prompt),
                }
            )
            return PromptPipelineResult(prompt, summary)
        raw_mode, raw_prompt = strip_raw_prefix(prompt)
        if raw_mode:
            self.logger.info("[comfyui_agent] prompt builder skipped: raw tags mode")
            summary.update(
                {
                    "raw_mode": True,
                    "skipped_reason": "raw_tags_mode",
                    "final_prompt_head": self._shorten(raw_prompt, 600),
                    "final_prompt_chars": len(raw_prompt),
                }
            )
            return PromptPipelineResult(raw_prompt, summary)

        prompt_config = apply_config_preset(dict(self.config))
        fixed_character = selected_fixed_character(prompt, prompt_config)
        fixed_character_name = fixed_character[0] if fixed_character else ""

        provider_id = await self._current_chat_provider_id(event)
        if not provider_id:
            self.logger.warning(
                "[comfyui_agent] prompt builder has no provider; using original prompt"
            )
            summary.update(
                {
                    "skipped_reason": "no_chat_provider",
                    "llm_failed": True,
                    "llm_error": "no_chat_provider",
                    "final_prompt_head": self._shorten(prompt, 600),
                    "final_prompt_chars": len(prompt),
                }
            )
            return PromptPipelineResult(prompt, summary)

        use_fixed_character = fixed_character is not None
        use_sensual_mode = wants_sensual_mode(prompt, prompt_config)
        outfit_plan = detect_outfit_transfer(prompt, fixed_character_name)
        required_core_tags = (
            self._danbooru_resolver.required_core_tags_for_prompt(prompt)
            if not use_fixed_character
            else ()
        )
        self.logger.info(
            "[comfyui_agent] prompt builder input fixed_character=%s sensual=%s required_core_tags=%s prompt=%s",
            fixed_character_name or "none",
            use_sensual_mode,
            ",".join(required_core_tags) or "none",
            prompt[:180],
        )
        research_plan = self._researcher.plan(prompt)
        self.logger.info(
            "[comfyui_agent] prompt strategy web_search=%s deep_thinking=%s search_reason=%s thinking_reason=%s",
            research_plan.use_web_search,
            research_plan.use_deep_thinking,
            research_plan.search_reason or "none",
            research_plan.thinking_reason or "none",
        )
        search_query_prompt = preferred_search_prompt(outfit_plan, prompt)
        search_context = (
            await self._researcher.search_context(
                event,
                prompt,
                search_query_prompt=search_query_prompt,
            )
            if research_plan.use_web_search
            else ""
        )
        if multi_person:
            multi_result = await self._build_multi_person_prompt(
                provider_id=provider_id,
                prompt=prompt,
                prompt_config=prompt_config,
                use_deep_thinking=research_plan.use_deep_thinking,
                summary=summary,
                original_user_prompt=background_intent_prompt,
            )
            if multi_result is not None:
                return multi_result
            summary.setdefault("multi_person_mode", True)
            summary.setdefault("multi_person_plan_failed", True)
            summary.setdefault("multi_person_error", "invalid_plan")
            summary.update(
                {
                    "skipped_reason": "multi_person_plan_failed",
                    "final_prompt_head": "",
                    "final_prompt_chars": 0,
                }
            )
            return PromptPipelineResult("", summary)
        outfit_summary = ""
        outfit_summary_source = ""
        reference_tag_text = (
            extract_reference_tag_text(prompt) if outfit_plan.enabled else ""
        )
        if reference_tag_text:
            outfit_summary = filter_outfit_tags(reference_tag_text, max_tags=42)
            if outfit_summary:
                outfit_summary_source = "reference_filter"
        if outfit_plan.enabled and not outfit_summary and search_context:
            summary_prompt = build_outfit_summary_prompt(
                outfit_plan,
                original_prompt=prompt,
                source_context=search_context,
            )
            try:
                raw_outfit_summary = await self._generate_outfit_summary_with_llm(
                    provider_id=provider_id,
                    summary_prompt=summary_prompt,
                    use_deep_thinking=research_plan.use_deep_thinking,
                )
                outfit_summary = filter_outfit_tags(raw_outfit_summary, max_tags=48)
                if outfit_summary:
                    outfit_summary_source = "search_summary"
                if self._bool("debug_prompt_enabled", False):
                    self.logger.info(
                        "[comfyui_agent] outfit summary LLM output:\n%s",
                        raw_outfit_summary,
                    )
            except Exception as exc:
                self.logger.warning(
                    "[comfyui_agent] outfit summary build failed: %s", exc
                )
        llm_prompt = build_llm_prompt(
            prompt,
            search_context=search_context,
            fixed_character=use_fixed_character,
            character_name=fixed_character_name,
            sensual_mode=use_sensual_mode,
            mode=mode,
            prompt_builder_template=self._str("prompt_builder_template", ""),
            outfit_transfer_rule=build_outfit_transfer_block(
                outfit_plan, outfit_summary
            ),
            original_theme=background_intent_prompt,
        )
        if self._bool("debug_prompt_enabled", False):
            self.logger.info(
                "[comfyui_agent] prompt builder LLM prompt:\n%s", llm_prompt
            )
        llm_content = ""
        llm_error = ""
        try:
            llm_content = await self._generate_prompt_tags_with_llm(
                provider_id=provider_id,
                llm_prompt=llm_prompt,
                use_deep_thinking=research_plan.use_deep_thinking,
                fixed_character=use_fixed_character,
                character_name=fixed_character_name,
            )
        except Exception as exc:
            if not research_plan.use_deep_thinking:
                self.logger.warning(
                    "[comfyui_agent] prompt builder LLM failed: %s", exc
                )
                llm_error = str(exc)
                llm_content = ""
            else:
                self.logger.warning(
                    "[comfyui_agent] prompt builder deep thinking failed, retrying without it: %s",
                    exc,
                )
                try:
                    llm_content = await self._generate_prompt_tags_with_llm(
                        provider_id=provider_id,
                        llm_prompt=llm_prompt,
                        use_deep_thinking=False,
                        fixed_character=use_fixed_character,
                        character_name=fixed_character_name,
                    )
                except Exception as retry_exc:
                    self.logger.warning(
                        "[comfyui_agent] prompt builder LLM failed: %s", retry_exc
                    )
                    llm_error = str(retry_exc)
                    llm_content = ""

        if self._bool("debug_prompt_enabled", False):
            self.logger.info(
                "[comfyui_agent] prompt builder LLM output:\n%s", llm_content
            )
        background_mode = ""
        background_mode_source = "not_applicable"
        if mode == "txt2img":
            llm_content, background_mode = extract_background_mode(llm_content)
            if background_mode:
                background_mode_source = "llm_marker"
            else:
                background_mode = DEFAULT_PORTRAIT
                background_mode_source = "missing_marker_default"
        llm_failed = bool(llm_error and not str(llm_content or "").strip())
        character_resolution = await self._danbooru_resolver.resolve_detailed(
            llm_content=llm_content,
            user_prompt=prompt,
            fixed_character=use_fixed_character,
        )
        if not use_fixed_character and (
            character_resolution.status == "unresolved"
            or (character_resolution.explicit_request and not required_core_tags)
        ):
            try:
                candidate_hints = await self._generate_character_candidates_with_llm(
                    provider_id=provider_id,
                    user_prompt=prompt,
                    rejected_content=llm_content,
                )
            except Exception as exc:
                self.logger.warning(
                    "[comfyui_agent] character candidate planner failed: %s",
                    exc,
                )
                candidate_hints = ()
            if candidate_hints:
                character_resolution = await self._danbooru_resolver.resolve_detailed(
                    llm_content=llm_content,
                    user_prompt=prompt,
                    fixed_character=False,
                    candidate_hints=candidate_hints,
                )
        llm_content = character_resolution.text
        if character_resolution.identity_tags:
            required_core_tags = character_resolution.identity_tags
        low_cfg_harness = bool(prompt_config.get("low_cfg_harness_enabled", False))
        constraint_raw = ""
        constraint_plan = parse_constraint_plan("")
        if low_cfg_harness:
            try:
                constraint_raw = await self._generate_constraint_plan_with_llm(
                    provider_id=provider_id,
                    plan_prompt=build_constraint_plan_prompt(
                        user_prompt=prompt,
                        llm_content=llm_content or prompt,
                        fixed_character_name=fixed_character_name,
                    ),
                )
                constraint_plan = parse_constraint_plan(constraint_raw)
            except Exception as constraint_exc:
                self.logger.warning(
                    "[comfyui_agent] prompt constraint planner failed: %s",
                    constraint_exc,
                )
        built = build_final_prompt(
            user_prompt=prompt,
            llm_content=llm_content,
            config=prompt_config,
            required_core_tags=required_core_tags,
            constraint_plan=constraint_plan,
            background_mode=background_mode,
        )
        initial_input_tag_count = len(split_tags(llm_content))
        content_tag_count = len(split_tags(built.content_tags))
        removed_tag_count = max(0, initial_input_tag_count - content_tag_count)
        self.logger.info(
            "[comfyui_agent] prompt built raw=%s web_search=%s deep_thinking=%s character=%s sensual=%s fixed_character=%s default_style=%s low_cfg_harness=%s constraint=%s weighted_style=%s required_core_tags=%s content_tags=%s content_chars=%s final_chars=%s final_head=%s",
            built.raw_mode,
            bool(search_context),
            research_plan.use_deep_thinking,
            built.character_name or "none",
            built.used_sensual_mode,
            built.used_fixed_character,
            built.used_default_style,
            low_cfg_harness,
            built.constraint_mode,
            ",".join(built.weighted_style_tags) or "none",
            ",".join(built.required_core_tags) or "none",
            content_tag_count,
            len(built.content_tags),
            len(built.final_prompt),
            built.final_prompt[:300],
        )
        summary.update(
            {
                "raw_mode": built.raw_mode,
                "web_search": bool(search_context),
                "deep_thinking": research_plan.use_deep_thinking,
                "search_reason": research_plan.search_reason or "",
                "thinking_reason": research_plan.thinking_reason or "",
                "fixed_character": built.used_fixed_character,
                "fixed_character_name": built.character_name,
                "sensual_mode": built.used_sensual_mode,
                "default_style": built.used_default_style,
                "low_cfg_harness": low_cfg_harness,
                "background_mode": background_mode or "unresolved",
                "background_mode_source": background_mode_source,
                "constraint_mode": built.constraint_mode,
                "weighted_style_tags": list(built.weighted_style_tags),
                "constraint_tags": list(built.constraint_tags),
                "removed_constraint_tags": list(built.removed_constraint_tags),
                "constraint_reason": built.constraint_reason,
                "required_core_tags": list(built.required_core_tags),
                "named_character_detected": character_resolution.status
                in {"resolved", "unresolved", "source_unavailable"},
                "character_resolution_status": character_resolution.status,
                "character_canonical_tag": character_resolution.canonical_tag,
                "character_identity_tags": list(character_resolution.identity_tags),
                "character_candidate_hints": list(character_resolution.candidate_hints),
                "character_resolution_evidence": list(character_resolution.evidence),
                "outfit_transfer": outfit_plan.enabled,
                "outfit_transfer_source": outfit_plan.source_subject,
                "outfit_transfer_target": outfit_plan.target_character,
                "outfit_summary_source": outfit_summary_source,
                "outfit_summary_chars": len(outfit_summary),
                "llm_failed": llm_failed,
                "llm_error": self._shorten(llm_error, 300),
                "llm_content_tag_count": content_tag_count,
                "removed_content_tag_count": removed_tag_count,
                "llm_content_chars": len(built.content_tags),
                "final_prompt_chars": len(built.final_prompt),
                "final_prompt_head": self._shorten(built.final_prompt, 600),
                "prompt_builder_template_customized": bool(
                    self._str("prompt_builder_template", "").strip()
                ),
            }
        )
        if self._bool("debug_prompt_enabled", False):
            self.logger.info(
                "[comfyui_agent] prompt builder final prompt:\n%s", built.final_prompt
            )
            summary.update(
                {
                    "llm_prompt": llm_prompt,
                    "outfit_summary": outfit_summary,
                    "constraint_plan": constraint_raw,
                    "llm_content": llm_content,
                    "final_prompt": built.final_prompt,
                }
            )
        return PromptPipelineResult(built.final_prompt, summary)
