from __future__ import annotations

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
    from .prompt_constraints import build_constraint_plan_prompt, parse_constraint_plan
    from .prompt_presets import (
        active_style_preset_name,
        apply_config_preset,
        looks_like_danbooru_tags,
        selected_fixed_character,
        strip_raw_prefix,
        wants_sensual_mode,
    )
    from .prompt_research import PromptResearcher
    from .prompt_templates import build_llm_prompt
    from .tag_cleaner import split_tags
except Exception:  # pragma: no cover - fallback for direct script-style imports.
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
    from prompt_constraints import build_constraint_plan_prompt, parse_constraint_plan
    from prompt_presets import (
        active_style_preset_name,
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

    def _try_direct_prompt_path(self, prompt: str, trace: Any) -> str | None:
        """Return prompt unchanged for disabled optimization or tag-like input."""
        text = str(prompt or "").strip()
        if not self._bool("prompt_optimize_enabled", True):
            trace.mark_skipped("prompt_optimize_disabled", text)
            return text
        if looks_like_danbooru_tags(text):
            trace.mark_raw("danbooru_tags_detected", text, danbooru_fast_path=True)
            return text
        return None

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
                "用户没有使用固定角色时，可以并且应该输出主体所需的固有外观设定。"
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
        kwargs: dict[str, Any] = {
            "chat_provider_id": provider_id,
            "prompt": plan_prompt,
            "system_prompt": (
                "You are a strict JSON planner for anime image prompt constraints. "
                "Return only valid JSON. Do not output Markdown or explanations."
            ),
            "max_tokens": 450,
        }
        response = await self.context.llm_generate(**kwargs)
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
        prompt = str(user_prompt or "").strip()
        summary: dict[str, Any] = {
            "prompt_optimize_enabled": self._bool("prompt_optimize_enabled", True),
            "mode": mode,
            "original_prompt_head": self._shorten(prompt, 600),
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

        provider_id = await self._current_chat_provider_id(event)
        if not provider_id:
            self.logger.warning(
                "[comfyui_agent] prompt builder has no provider; using original prompt"
            )
            summary.update(
                {
                    "skipped_reason": "no_chat_provider",
                    "final_prompt_head": self._shorten(prompt, 600),
                    "final_prompt_chars": len(prompt),
                }
            )
            return PromptPipelineResult(prompt, summary)

        prompt_config = apply_config_preset(dict(self.config))
        star_knight_style = active_style_preset_name(prompt_config).startswith(
            "闪耀星骑士"
        )
        fixed_character = selected_fixed_character(prompt, prompt_config)
        fixed_character_name = fixed_character[0] if fixed_character else ""
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
            style_block=(
                "-----------\n"
                "当前启用闪耀星骑士角色立绘风格。请先在内部从梦幻偶像、暗黑魔法、科技魔女、东方幻想中选择最符合用户主题的一个子风格；只保留一个主方向。\n"
                "优先输出角色身份、发型脸部、服装主结构、大型装备、主色和材质，再补充动作与少量光影。\n"
                "保持高端二次元手游全身立绘：清晰轮廓、干净线稿、平涂与柔和渐变阴影结合、精致材质高光。不要主动添加复杂背景、摄影镜头或互相冲突的颜色。\n"
                "画师组已经提供风格参考，不要在内容 tags 中重复画师名；具体内容控制在约 35-60 个高信息密度 tags。"
                if star_knight_style
                else ""
            ),
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
        llm_failed = bool(llm_error and not str(llm_content or "").strip())
        llm_content = await self._danbooru_resolver.resolve(
            llm_content=llm_content,
            user_prompt=prompt,
            fixed_character=use_fixed_character,
        )
        constraint_raw = ""
        constraint_plan = parse_constraint_plan("")
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
                "[comfyui_agent] prompt constraint planner failed: %s", constraint_exc
            )
        built = build_final_prompt(
            user_prompt=prompt,
            llm_content=llm_content,
            config=prompt_config,
            required_core_tags=required_core_tags,
            constraint_plan=constraint_plan,
        )
        content_tag_count = len(split_tags(built.content_tags))
        short_content_retry = False
        minimum_content_tags = 35 if star_knight_style else 60
        if (
            not llm_failed
            and not built.raw_mode
            and not built.constraint_mode
            and content_tag_count < minimum_content_tags
        ):
            retry_prompt = (
                llm_prompt
                + "\n-----------\n"
                + "上一次输出的具体内容 tags 太短。请重新输出更完整的英文 Danbooru tags："
                + (
                    "目标 35-60 个高信息密度的具体内容 tags，重点补足服装主结构、材质、大型装备、主色和可见细节。"
                    if star_knight_style
                    else "目标 70-120 个具体内容 tags，重点扩写服装结构、材质、纹样、饰品、姿态、表情、手部动作和可见细节。"
                )
                + "不要输出质量词、画师词、解释或 Markdown。"
            )
            try:
                retry_content = await self._generate_prompt_tags_with_llm(
                    provider_id=provider_id,
                    llm_prompt=retry_prompt,
                    use_deep_thinking=False,
                    fixed_character=use_fixed_character,
                    character_name=fixed_character_name,
                )
                retry_content = await self._danbooru_resolver.resolve(
                    llm_content=retry_content,
                    user_prompt=prompt,
                    fixed_character=use_fixed_character,
                )
                retry_built = build_final_prompt(
                    user_prompt=prompt,
                    llm_content=retry_content,
                    config=prompt_config,
                    required_core_tags=required_core_tags,
                    constraint_plan=constraint_plan,
                )
                retry_tag_count = len(split_tags(retry_built.content_tags))
                if retry_tag_count > content_tag_count:
                    llm_content = retry_content
                    built = retry_built
                    content_tag_count = retry_tag_count
                    short_content_retry = True
            except Exception as retry_exc:
                self.logger.warning(
                    "[comfyui_agent] prompt builder short-content retry failed: %s",
                    retry_exc,
                )
        self.logger.info(
            "[comfyui_agent] prompt built raw=%s web_search=%s deep_thinking=%s character=%s sensual=%s fixed_character=%s default_style=%s constraint=%s weighted_style=%s required_core_tags=%s content_tags=%s content_chars=%s final_chars=%s final_head=%s",
            built.raw_mode,
            bool(search_context),
            research_plan.use_deep_thinking,
            built.character_name or "none",
            built.used_sensual_mode,
            built.used_fixed_character,
            built.used_default_style,
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
