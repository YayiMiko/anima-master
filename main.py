import sys
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr

try:
    from . import anima_verify
    from .command_router import parse_hard_route
    from .config_defaults import maybe_reset_to_defaults
    from .prompt_presets import apply_config_preset, maybe_materialize_chiyo_preset
    from .service_container import build_services
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    import anima_verify
    from command_router import parse_hard_route
    from config_defaults import maybe_reset_to_defaults
    from prompt_presets import apply_config_preset, maybe_materialize_chiyo_preset
    from service_container import build_services


class ComfyUIAgentPlugin(Star):
    """Basic local ComfyUI backend for AstrBot."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context, config)
        raw_or_reset = maybe_reset_to_defaults(
            config or {},
            Path(__file__).with_name("_conf_schema.json"),
        )
        raw_config = maybe_materialize_chiyo_preset(
            config if config is not None else raw_or_reset,
            base_config=raw_or_reset,
        )
        self.config = apply_config_preset(raw_config)
        self._danbooru_tag_cache: dict[str, list[Any]] = {}
        self._last_prompt_summary: dict[str, Any] = {}
        self._services = build_services(
            context=self.context,
            config=self.config,
            config_store=config,
            logger=logger,
            danbooru_tag_cache=self._danbooru_tag_cache,
            get_bool=self._bool,
            get_int=self._int,
            get_float=self._float,
            get_str=self._str,
            shorten=self._shorten,
            is_allowed=self._is_allowed,
            build_prompt=self._build_anima_prompt,
            prompt_summary=lambda: self._last_prompt_summary,
            generate=self._generate,
            edit=self._edit,
            remove_bg=self._remove_bg,
            spell=self._spell,
            reverse=self._reverse,
        )
        self._runtime = self._services.runtime
        self._prompt_pipeline = self._services.prompt_pipeline
        self._generation_task = self._services.generation_task
        self._action_handler = self._services.action_handler
        self._llm_tool_bridge = self._services.llm_tool_bridge

    async def initialize(self):
        img2img_enabled = self._bool("img2img_enabled", False)
        if img2img_enabled:
            edit_tool_changed = self.context.activate_llm_tool("comfyui_edit")
        else:
            edit_tool_changed = self.context.deactivate_llm_tool("comfyui_edit")
        remove_bg_tool_changed = self.context.deactivate_llm_tool("comfyui_remove_bg")
        logger.info(
            "[comfyui_agent] chiyo_preset_enabled=%s img2img_enabled=%s edit_tool_changed=%s remove_bg_tool_changed=%s base_url=%s workflow=%s",
            self._bool("chiyo_preset_enabled", False),
            img2img_enabled,
            edit_tool_changed,
            remove_bg_tool_changed,
            self._str("comfyui_base_url", "http://127.0.0.1:8188"),
            self._str("workflow", "anima_t2i"),
        )

    def _bool(self, key: str, default: bool) -> bool:
        return bool(self.config.get(key, default))

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _float(self, key: str, default: float) -> float:
        try:
            return float(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _str(self, key: str, default: str = "") -> str:
        value = self.config.get(key, default)
        return str(value if value is not None else default)

    def _is_allowed(self, event: AstrMessageEvent) -> bool:
        if self._bool("admin_only", False) and not event.is_admin():
            return False
        allowed = self.config.get("allowed_sender_ids", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        allowed_set = {str(item).strip() for item in allowed or [] if str(item).strip()}
        if allowed_set and str(event.get_sender_id()) not in allowed_set:
            return False
        return True

    async def _run_tool(self, args: list[str]) -> dict[str, Any]:
        return await self._runtime.run_tool(args)

    def _shorten(self, text: str, limit: int = 1800) -> str:
        text = str(text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n...[已截断]"

    async def _build_anima_prompt(
        self,
        event: AstrMessageEvent,
        user_prompt: str,
        mode: str = "txt2img",
    ) -> str:
        result = await self._prompt_pipeline.build(event, user_prompt, mode)
        self._last_prompt_summary = dict(result.summary)
        return result.final_prompt

    async def _ensure_comfyui_ready(self, event: AstrMessageEvent) -> dict[str, Any]:
        return await self._runtime.ensure_ready(event)

    async def _send_payload(self, event: AstrMessageEvent, payload: dict[str, Any]) -> str:
        return await self._runtime.send_payload(event, payload)

    async def _verify_provider_id(self, event: AstrMessageEvent) -> str:
        """Resolve the provider used for image self-verification.

        Prefers the plugin's ``verify_provider_id`` config, then falls back to
        the session's image-caption / default chat provider (same resolution
        used by reference-image reverse tagging).
        """
        configured = self._str("verify_provider_id", "").strip()
        if configured:
            return configured
        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            provider_settings = cfg.get("provider_settings", {})
            return str(
                provider_settings.get("default_image_caption_provider_id")
                or provider_settings.get("default_provider_id")
                or ""
            ).strip()
        except Exception:  # noqa: BLE001
            return ""

    def _make_verify_llm_call(self, provider_id: str):
        """Build the ``(prompt, image_urls) -> str`` caller for verification."""

        async def llm_call(prompt: str, image_urls=None) -> str:
            if not provider_id:
                raise RuntimeError("no_verify_provider_available")
            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=anima_verify.ANIMA_VERIFY_SYSTEM,
                image_urls=image_urls or None,
                max_tokens=self._int("prompt_builder_max_tokens", 700),
            )
            return str(getattr(resp, "completion_text", "") or "")

        return llm_call

    async def _generate_payload(
        self,
        event: AstrMessageEvent,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        negative_prompt: str | None = None,
    ) -> dict[str, Any]:
        return await self._generation_task.generate_payload(
            event,
            prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            negative_prompt=negative_prompt,
        )

    async def _generate(
        self,
        event: AstrMessageEvent,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        negative_prompt: str | None = None,
    ) -> str:
        payload = await self._generate_payload(
            event,
            prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            negative_prompt=negative_prompt,
        )

        # Self-verification: look at the generated image and, if it does not
        # match the request, adjust the prompt and retry once before sending.
        verdict = await self._verify_and_maybe_retry(
            event,
            payload,
            user_request=prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            negative_prompt=negative_prompt,
        )
        payload = verdict["payload"]

        message = await self._send_payload(event, payload)
        # Surface silent prompt-optimiser failures to the user so they know
        # the image was drawn from the raw request, not the crafted tags.
        if payload.get("ok") and not self._last_prompt_summary.get("llm_ok", True):
            await event.send(event.plain_result(
                "（提示词优化这次没走通，是拿你的原文直接画的，可能不太准。要重画就再说一次。）"
            ))
        # If verification still failed after the retry, tell the user what
        # looked off and let them decide whether to redraw.
        final = verdict.get("verdict")
        if payload.get("ok") and final is not None and not final.passed and not final.skipped:
            issues = "；".join(final.issues[:3]) if final.issues else "和描述有出入"
            await event.send(event.plain_result(
                f"（这张我看着还差点意思：{issues}。要再调整重画就说一声。）"
            ))
        return message

    async def _verify_and_maybe_retry(
        self,
        event: AstrMessageEvent,
        payload: dict[str, Any],
        *,
        user_request: str,
        width: int | None,
        height: int | None,
        steps: int | None,
        cfg: float | None,
        negative_prompt: str | None,
    ) -> dict[str, Any]:
        """Verify the generated image; retry once with a fix hint if needed.

        Returns a dict ``{"payload": <best payload>, "verdict": <Verdict|None>}``.
        Verification is skipped (verdict None) when disabled, when generation
        failed, or when the backend produced no output image.
        """
        result: dict[str, Any] = {"payload": payload, "verdict": None}
        if not self._bool("enable_verify", True):
            return result
        if not payload.get("ok"):
            return result
        outputs = [str(p) for p in (payload.get("outputs") or []) if str(p).strip()]
        if not outputs:
            return result

        provider_id = await self._verify_provider_id(event)
        if not provider_id:
            logger.info("[comfyui_agent] verify skipped: no provider available")
            return result
        llm_call = self._make_verify_llm_call(provider_id)
        pass_score = self._int("verify_pass_score", 7)
        max_retry = max(0, self._int("max_verify_retry", 1))

        verdict = await anima_verify.verify_image(
            llm_call, outputs[-1], user_request, pass_score=pass_score
        )
        result["verdict"] = verdict
        logger.info(
            "[comfyui_agent] verify: passed=%s score=%s skipped=%s",
            verdict.passed, verdict.score, verdict.skipped,
        )

        retries = 0
        while not verdict.passed and not verdict.skipped and retries < max_retry:
            retries += 1
            hint = verdict.fix_hint or ("；".join(verdict.issues) if verdict.issues else "")
            logger.info("[comfyui_agent] verify retry %s with hint: %s", retries, hint)
            retry_prompt = user_request
            if hint:
                retry_prompt = f"{user_request}\n【上次问题，请修正】{hint}"
            retry_payload = await self._generate_payload(
                event,
                retry_prompt,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                negative_prompt=negative_prompt,
            )
            if not retry_payload.get("ok"):
                # Retry generation failed outright — keep the first good image.
                break
            retry_outputs = [str(p) for p in (retry_payload.get("outputs") or []) if str(p).strip()]
            if not retry_outputs:
                break
            result["payload"] = retry_payload
            verdict = await anima_verify.verify_image(
                llm_call, retry_outputs[-1], user_request, pass_score=pass_score
            )
            result["verdict"] = verdict
            logger.info(
                "[comfyui_agent] verify(after retry %s): passed=%s score=%s",
                retries, verdict.passed, verdict.score,
            )
        return result

    async def _edit(self, event: AstrMessageEvent, prompt: str) -> str:
        return await self._action_handler.edit(event, prompt)

    async def _spell(self, event: AstrMessageEvent) -> str:
        return await self._action_handler.spell(event)

    async def _reverse(self, event: AstrMessageEvent) -> str:
        return await self._action_handler.reverse(event)

    async def _upscale(self, event: AstrMessageEvent) -> str:
        return await self._action_handler.upscale(event)

    async def _remove_bg(self, event: AstrMessageEvent) -> str:
        return await self._action_handler.remove_bg(event)

    def _status_text(self, payload: dict[str, Any]) -> str:
        return self._action_handler.status_text(payload)

    async def _handle_action(self, event: AstrMessageEvent, action: str, prompt: str) -> str | None:
        return await self._action_handler.handle_action(event, action, prompt)

    @filter.command_group("anm", alias={"comfyui", "anima"})
    def comfyui_group(self):
        pass

    @filter.event_message_type(EventMessageType.ALL, priority=sys.maxsize - 2)
    async def hard_route_comfyui(self, event: AstrMessageEvent):
        route = parse_hard_route(event.get_message_str())
        if not route:
            route = parse_hard_route(event.get_message_outline())
        if not route:
            return
        if not self._is_allowed(event):
            await event.send(event.plain_result("ComfyUI 助手已关闭，或当前用户没有使用权限。"))
            event.stop_event()
            return

        action, prompt = route
        logger.info("[comfyui_agent] hard route action=%s sender=%s", action, event.get_sender_id())
        event.stop_event()

        message = await self._handle_action(event, action, prompt)
        if message:
            await event.send(event.plain_result(message))

    @comfyui_group.command("status", alias={"状态"})
    async def cmd_status(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "status", ""))

    @comfyui_group.command("debug", alias={"调试状态", "调试", "debug_status"})
    async def cmd_debug_status(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "debug_status", ""))

    @comfyui_group.command("generate", alias={"生图", "画图"})
    async def cmd_generate(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        message = await self._handle_action(event, "generate", str(prompt or "").strip())
        if message:
            yield event.plain_result(message)

    @comfyui_group.command("edit", alias={"改图", "图生图", "风格化", "重绘"})
    async def cmd_edit(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "edit", str(prompt or "").strip()))

    @comfyui_group.command("upscale", alias={"放大", "高清", "高清修复"})
    async def cmd_upscale(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "disabled_upscale", ""))

    @comfyui_group.command("remove_bg", alias={"抠图", "去背景", "去除背景"})
    async def cmd_remove_bg(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "disabled_remove_bg", ""))

    @comfyui_group.command("spell", alias={"解析法术", "法术解析", "读取法术", "提取提示词", "读取提示词"})
    async def cmd_spell(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "spell", ""))

    @comfyui_group.command("reverse", alias={"反推", "图片反推", "反推提示词"})
    async def cmd_reverse(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "reverse", ""))

    @comfyui_group.command(
        "artist",
        alias={
            "创建画师组",
        },
    )
    async def cmd_set_artist_tags(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "create_artist_preset", str(prompt or "").strip()))

    @comfyui_group.command("append_artist", alias={"追加画师组"})
    async def cmd_append_artist_tags(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "append_artist_tags", str(prompt or "").strip()))

    @comfyui_group.command("use_artist", alias={"切换画师组"})
    async def cmd_use_artist_preset(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "use_artist_preset", str(prompt or "").strip()))

    @comfyui_group.command("list_artist", alias={"查看画师组"})
    async def cmd_list_artist_presets(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "list_artist_presets", ""))

    @comfyui_group.command("delete_artist", alias={"删除画师组"})
    async def cmd_delete_artist_preset(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "delete_artist_preset", str(prompt or "").strip()))

    @comfyui_group.command(
        "character",
        alias={
            "添加角色",
        },
    )
    async def cmd_add_fixed_character(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        yield event.plain_result(await self._handle_action(event, "add_fixed_character", str(prompt or "").strip()))

    @filter.llm_tool(name="comfyui_status")
    async def comfyui_status(self, event: AstrMessageEvent) -> str:
        """Check whether local ComfyUI is online and ready.

        Args:
        """
        return await self._llm_tool_bridge.status(event)

    @filter.llm_tool(name="comfyui_generate")
    async def comfyui_generate(
        self,
        event: AstrMessageEvent,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        negative_prompt: str | None = None,
    ) -> str:
        """Generate an image with local ComfyUI from the provided prompt/tags.

        Args:
            prompt(string): Complete prompt or tags to send to ComfyUI unchanged.
            width(number): Optional width from the allowed size list.
            height(number): Optional height paired with width.
            steps(number): Optional sampling steps.
            cfg(number): Optional CFG scale.
            negative_prompt(string): Optional negative prompt to use for this generation.
        """
        return await self._llm_tool_bridge.generate(
            event,
            prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            negative_prompt=negative_prompt,
        )

    @filter.llm_tool(name="comfyui_edit")
    async def comfyui_edit(self, event: AstrMessageEvent, prompt: str) -> str:
        """Edit the most recent chat image with local ComfyUI img2img.

        Args:
            prompt(string): Complete img2img prompt or tags.
        """
        return await self._llm_tool_bridge.edit(event, prompt)

    @filter.llm_tool(name="comfyui_remove_bg")
    async def comfyui_remove_bg(self, event: AstrMessageEvent) -> str:
        """Remove the background from the most recent chat image with local ComfyUI.

        Args:
        """
        return await self._llm_tool_bridge.remove_bg(event)

    @filter.llm_tool(name="comfyui_extract_prompt")
    async def comfyui_extract_prompt(self, event: AstrMessageEvent) -> str:
        """Extract embedded generation prompt/metadata from the most recent or quoted image.

        Args:
        """
        return await self._llm_tool_bridge.extract_prompt(event)

    @filter.llm_tool(name="comfyui_reverse_prompt")
    async def comfyui_reverse_prompt(self, event: AstrMessageEvent) -> str:
        """Reverse-engineer danbooru tags from the most recent or quoted image using a vision model.

        Args:
        """
        return await self._llm_tool_bridge.reverse_prompt(event)
