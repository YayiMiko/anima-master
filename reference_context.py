from typing import Any, Awaitable, Callable

from astrbot.api.event import AstrMessageEvent


class ReferenceContextBuilder:
    """Build prompt-ready context from a referenced image."""

    def __init__(
        self,
        *,
        context: Any,
        run_prompt_tool: Callable[[list[str]], Awaitable[dict[str, Any]]],
        event_image_input: Callable[[AstrMessageEvent], Awaitable[str | None]],
        logger: Any,
        get_int: Callable[[str, int], int],
        shorten: Callable[[str, int], str],
    ):
        """Create a reference context builder.

        Args:
            context: AstrBot plugin context, used for LLM calls.
            run_prompt_tool: Async runner for image prompt helper commands.
            event_image_input: Async resolver for the current or quoted image.
            logger: Logger-like object used for diagnostics.
            get_int: Config integer getter.
            shorten: Function used to shorten long debug strings.
        """
        self._context = context
        self._run_prompt_tool = run_prompt_tool
        self._event_image_input = event_image_input
        self._logger = logger
        self._get_int = get_int
        self._shorten = shorten
        self.last_summary: dict[str, Any] = {}

    async def _image_caption_provider_id(self, event: AstrMessageEvent) -> str:
        cfg = self._context.get_config(umo=event.unified_msg_origin)
        provider_settings = cfg.get("provider_settings", {})
        return str(
            provider_settings.get("default_image_caption_provider_id")
            or provider_settings.get("default_provider_id")
            or ""
        ).strip()

    async def image_spell_payload(
        self,
        event: AstrMessageEvent,
        image_input: str | None = None,
    ) -> dict[str, Any]:
        """Inspect embedded generation metadata from an image.

        Args:
            event: Current AstrBot message event.
            image_input: Optional already-resolved local image path.

        Returns:
            Prompt helper payload.
        """
        image_input = image_input or await self._event_image_input(event)
        args = ["inspect"]
        if image_input:
            args.extend(["--input", image_input])
        else:
            args.extend(["--input", "latest"])
        return await self._run_prompt_tool(args)

    async def reverse_image_tags(
        self,
        event: AstrMessageEvent,
        image_input: str | None = None,
    ) -> str:
        """Reverse-engineer danbooru tags from an image with a vision model.

        Args:
            event: Current AstrBot message event.
            image_input: Optional already-resolved local image path.

        Returns:
            English danbooru tags, or an empty string when unavailable.
        """
        image_input = image_input or await self._event_image_input(event)
        if not image_input:
            image_input = "latest"
        provider_id = await self._image_caption_provider_id(event)
        if not provider_id:
            return ""
        prompt = (
            "请反推这张二次元图片的生图提示词。"
            "输出英文 danbooru tags，用英文逗号分隔；不要解释，不要 Markdown。"
            "优先描述主体、角色外观、服饰、动作、神态、构图、背景、画风和质量观感。"
            "不要臆造网页出处，不要输出中文。"
        )
        try:
            response = await self._context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                image_urls=[image_input],
                max_tokens=self._get_int("prompt_builder_max_tokens", 700),
            )
            return str(getattr(response, "completion_text", "") or "").strip()
        except Exception as exc:
            self._logger.warning("[comfyui_agent] reverse image tags failed: %s", exc)
            return ""

    async def reference_prompt_context(
        self,
        event: AstrMessageEvent,
        image_input: str,
    ) -> str:
        """Build prompt context from an image.

        Args:
            event: Current AstrBot message event.
            image_input: Resolved local image path.

        Returns:
            Prompt-ready reference context. Empty means no usable context.
        """
        self.last_summary = {
            "image_input": image_input,
            "reference_context_method": "none",
            "reference_context_chars": 0,
            "spell_ok": False,
            "reverse_ok": False,
        }
        payload = await self.image_spell_payload(event, image_input)
        positive = str(payload.get("positive_prompt") or "").strip() if payload.get("ok") else ""
        self.last_summary["spell_ok"] = bool(positive)
        if positive:
            context = "参考图原始正面提示词：\n" + self._shorten(positive, 2200)
            self.last_summary.update(
                {
                    "reference_context_method": "spell",
                    "reference_context_chars": len(context),
                    "metadata_format": payload.get("metadata_format") or "",
                }
            )
            return context

        reverse = await self.reverse_image_tags(event, image_input)
        self.last_summary["reverse_ok"] = bool(reverse)
        if reverse:
            context = "参考图视觉反推 tags：\n" + self._shorten(reverse, 1800)
            self.last_summary.update(
                {
                    "reference_context_method": "reverse",
                    "reference_context_chars": len(context),
                }
            )
            return context
        return ""
