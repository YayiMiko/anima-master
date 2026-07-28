from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from .danbooru_resolver import DanbooruResolver
    from .outfit_transfer import (
        build_outfit_summary_prompt,
        build_outfit_transfer_block,
        detect_outfit_transfer,
        extract_reference_tag_text,
        filter_outfit_tags,
        preferred_search_prompt,
    )
    from .prompt_builder import (
        build_final_prompt,
    )
    from .prompt_constraints import (
        apply_scene_gate,
        build_constraint_plan_prompt,
        parse_constraint_plan,
        retry_preserves_prompt,
        scene_gate_open,
    )
    from .prompt_presets import (
        apply_config_preset,
        looks_like_danbooru_tags,
        selected_fixed_character,
        strip_raw_prefix,
        wants_sensual_mode,
    )
    from .prompt_research import PromptResearcher
    from .prompt_templates import build_llm_prompt
    from .tag_cleaner import split_tags
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from danbooru_resolver import DanbooruResolver
    from outfit_transfer import (
        build_outfit_summary_prompt,
        build_outfit_transfer_block,
        detect_outfit_transfer,
        extract_reference_tag_text,
        filter_outfit_tags,
        preferred_search_prompt,
    )
    from prompt_builder import (
        build_final_prompt,
    )
    from prompt_constraints import (
        apply_scene_gate,
        build_constraint_plan_prompt,
        parse_constraint_plan,
        retry_preserves_prompt,
        scene_gate_open,
    )
    from prompt_presets import (
        apply_config_preset,
        looks_like_danbooru_tags,
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
        creative_expansion: bool = False,
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
            "本次启用自由发挥模式：在严格保留用户明确要求和角色身份的前提下，"
            "主动发展统一主题并补充服装结构、材质配饰、姿态手势、前景互动、构图、光影和少量特效，"
            "目标为50至65个不重复的可见内容tag；背景保持简洁。"
            if creative_expansion
            else ""
        )
        scene_scope_rule = (
            ""
            if creative_expansion
            else (
                "非自由发挥模式必须执行场景类Tag门控：先判断用户是否明确提到前景互动、构图镜头、"
                "环境背景、光影、特效氛围中的任意一类。若均未提及，禁止生成这五类Tag，"
                "只写主体关系、角色、服装材质配饰、动作手势、神态视线，且不设最低Tag数量；"
                "若提到任意一类，才可以按需生成全部场景类型。"
            )
        )
        kwargs: dict[str, Any] = {
            "chat_provider_id": provider_id,
            "prompt": llm_prompt,
            "system_prompt": (
                "你是 Anima 模型的 Danbooru tag 提示词助手。"
                "请在内部充分推理和校验参考对象的视觉特征，但不要输出思考过程。"
                "只输出英文 danbooru tags，用英文逗号分隔。"
                "不要解释，不要 Markdown，不要输出质量词或画师词。"
                f"{character_rule}"
                f"{creative_rule}"
                f"{scene_scope_rule}"
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

    async def build(
        self, event: Any, user_prompt: str, mode: str = "txt2img"
    ) -> PromptPipelineResult:
        """Build the final prompt and summary for one generation request.

        Args:
            event: AstrBot message event for provider and per-chat config lookup.
            user_prompt: User prompt after reference-image augmentation.
            mode: Generation mode, such as `txt2img` or `img2img`.

        Returns:
            Final prompt plus a serializable summary dict.
        """
        original_prompt = str(user_prompt or "").strip()
        creative_expansion_re = re.compile(
            r"(?<!\S)--(?:自由发挥|自由拓展|创意拓展|创意扩展|creative)"
            r"(?=$|\s|[,，;；:：])",
            re.IGNORECASE,
        )
        creative_expansion = bool(creative_expansion_re.search(original_prompt))
        prompt = creative_expansion_re.sub(" ", original_prompt).strip()
        prompt = re.sub(r"^[\s,，;；:：]+|[\s,，;；:：]+$", "", prompt)
        prompt = re.sub(r"([,，;；])\s*[,，;；]+", r"\1", prompt)
        prompt = re.sub(r"\s+", " ", prompt)
        summary: dict[str, Any] = {
            "prompt_optimize_enabled": self._bool("prompt_optimize_enabled", True),
            "mode": mode,
            "original_prompt_head": self._shorten(original_prompt, 600),
            "creative_expansion": creative_expansion,
            "scene_gate_open": scene_gate_open(prompt, creative_expansion),
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
        if looks_like_danbooru_tags(prompt) and not creative_expansion:
            direct_content = ", ".join(
                tag
                for tag in split_tags(prompt)
                if not fixed_character_name
                or tag.strip().lower() != fixed_character_name.lower()
            )
            built = build_final_prompt(
                user_prompt=prompt,
                llm_content=direct_content,
                config=prompt_config,
            )
            content_tag_count = len(split_tags(built.content_tags))
            self.logger.info(
                "[comfyui_agent] prompt builder used Danbooru tag fast path character=%s content_tags=%s final_chars=%s",
                built.character_name or "none",
                content_tag_count,
                len(built.final_prompt),
            )
            summary.update(
                {
                    "raw_mode": False,
                    "danbooru_fast_path": True,
                    "skipped_reason": "danbooru_tags_detected",
                    "fixed_character": built.used_fixed_character,
                    "fixed_character_name": built.character_name,
                    "sensual_mode": built.used_sensual_mode,
                    "default_style": built.used_default_style,
                    "llm_failed": False,
                    "llm_error": "",
                    "llm_content_tag_count": content_tag_count,
                    "short_content_retry": False,
                    "llm_content_chars": len(built.content_tags),
                    "final_prompt_chars": len(built.final_prompt),
                    "final_prompt_head": self._shorten(built.final_prompt, 600),
                }
            )
            return PromptPipelineResult(built.final_prompt, summary)

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
            creative_expansion=creative_expansion,
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
                creative_expansion=creative_expansion,
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
                        creative_expansion=creative_expansion,
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
        llm_failed = bool(llm_error and not str(llm_content or "").strip())
        llm_content = await self._danbooru_resolver.resolve(
            llm_content=llm_content,
            user_prompt=prompt,
            fixed_character=use_fixed_character,
        )
        scene_allowed = scene_gate_open(prompt, creative_expansion)
        llm_content, removed_scene_tags = apply_scene_gate(
            llm_content,
            enabled=scene_allowed,
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
        )
        initial_input_tag_count = len(split_tags(llm_content))
        content_tag_count = len(split_tags(built.content_tags))
        removed_tag_count = max(0, initial_input_tag_count - content_tag_count)
        short_content_retry = False
        detail_refill_retry = False
        detail_refill_reason = ""
        if (
            not llm_failed
            and not built.raw_mode
            and not built.constraint_mode
            and not low_cfg_harness
            and (
                (creative_expansion and content_tag_count < 48)
                or (not creative_expansion and scene_allowed and content_tag_count < 35)
                or removed_tag_count >= 4
            )
        ):
            reasons: list[str] = []
            if creative_expansion and content_tag_count < 48:
                reasons.append("自由发挥模式细节不足")
            elif scene_allowed and content_tag_count < 35:
                reasons.append("内容不足")
            if removed_tag_count >= 4:
                reasons.append("同义或无效内容较多")
            detail_refill_reason = "、".join(reasons)
            retry_prompt = (
                llm_prompt
                + "\n-----------\n"
                + f"上一次输出需要重新分配细节，原因：{detail_refill_reason}。\n"
                + f"清理后的可用 tags：{built.content_tags}\n"
                + "请重写一份完整列表，不要只在末尾追加。合并同义词后，把空出的篇幅用于不同的可见画面槽位："
                + "主体与关键物件关系、主要动作和手势、相容神态、服装结构、材质纹样与配饰、前景互动元素、简洁背景层次、构图镜头、功能不同的光影、特效。"
                + (
                    ""
                    if creative_expansion
                    else "其中前景互动、背景、构图镜头、光影和特效仍受场景类Tag门控：用户五类均未提及时必须全部省略，只补充角色、服装、动作和神态细节。"
                )
                + "同一语义簇最多保留 1-2 个词；光源、光束、轮廓光、投影和空气粒子可以分别描述，但不要用多个词反复表达单纯的明亮或发光。"
                + (
                    "本次自由发挥模式使用 50-65 个具体、相容且不重复的内容 tags。"
                    if creative_expansion
                    else "仅在用户打开场景类门控时参考常规 40-55 个内容 tags；未打开时不设最低数量，不得为凑数补入场景类Tag或同义词。"
                )
                + "优先增加人物、服装、手部、物件关系和前景细节，背景只增加少量有区分度的元素。"
                + "不得替换用户明确的主体、花卉、道具、动作、表情、输出类型或镜头，也不要添加无关道具和冲突神态。"
                + "不要输出质量词、画师词、解释或 Markdown。"
            )
            try:
                retry_content = await self._generate_prompt_tags_with_llm(
                    provider_id=provider_id,
                    llm_prompt=retry_prompt,
                    use_deep_thinking=False,
                    fixed_character=use_fixed_character,
                    character_name=fixed_character_name,
                    creative_expansion=creative_expansion,
                )
                retry_content = await self._danbooru_resolver.resolve(
                    llm_content=retry_content,
                    user_prompt=prompt,
                    fixed_character=use_fixed_character,
                )
                retry_content, retry_removed_scene_tags = apply_scene_gate(
                    retry_content,
                    enabled=scene_allowed,
                )
                retry_built = build_final_prompt(
                    user_prompt=prompt,
                    llm_content=retry_content,
                    config=prompt_config,
                    required_core_tags=required_core_tags,
                    constraint_plan=constraint_plan,
                )
                retry_input_tag_count = len(split_tags(retry_content))
                retry_tag_count = len(split_tags(retry_built.content_tags))
                retry_removed_tag_count = max(
                    0, retry_input_tag_count - retry_tag_count
                )
                if (
                    retry_preserves_prompt(
                        original_tags=built.content_tags,
                        retry_tags=retry_built.content_tags,
                        required_core_tags=required_core_tags,
                        removed_scene_tags=retry_removed_scene_tags,
                    )
                    and retry_tag_count >= content_tag_count
                    and (
                        retry_tag_count > content_tag_count
                        or retry_removed_tag_count < removed_tag_count
                    )
                ):
                    llm_content = retry_content
                    built = retry_built
                    content_tag_count = retry_tag_count
                    removed_tag_count = retry_removed_tag_count
                    short_content_retry = "内容不足" in reasons
                    detail_refill_retry = True
            except Exception as retry_exc:
                self.logger.warning(
                    "[comfyui_agent] prompt builder detail-refill retry failed: %s",
                    retry_exc,
                )
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
                "creative_expansion": creative_expansion,
                "scene_gate_open": scene_allowed,
                "removed_scene_tags": list(removed_scene_tags),
                "low_cfg_harness": low_cfg_harness,
                "constraint_mode": built.constraint_mode,
                "weighted_style_tags": list(built.weighted_style_tags),
                "constraint_tags": list(built.constraint_tags),
                "removed_constraint_tags": list(built.removed_constraint_tags),
                "constraint_reason": built.constraint_reason,
                "required_core_tags": list(built.required_core_tags),
                "outfit_transfer": outfit_plan.enabled,
                "outfit_transfer_source": outfit_plan.source_subject,
                "outfit_transfer_target": outfit_plan.target_character,
                "outfit_summary_source": outfit_summary_source,
                "outfit_summary_chars": len(outfit_summary),
                "llm_failed": llm_failed,
                "llm_error": self._shorten(llm_error, 300),
                "llm_content_tag_count": content_tag_count,
                "short_content_retry": short_content_retry,
                "detail_refill_attempted": bool(detail_refill_reason),
                "detail_refill_retry": detail_refill_retry,
                "detail_refill_reason": detail_refill_reason,
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
