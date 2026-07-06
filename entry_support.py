from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star

try:
    from .config_defaults import maybe_reset_to_defaults
    from .prompt_presets import apply_config_preset, maybe_materialize_chiyo_preset
    from .service_container import build_services
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from config_defaults import maybe_reset_to_defaults
    from prompt_presets import apply_config_preset, maybe_materialize_chiyo_preset
    from service_container import build_services


def initialize_plugin_config(config: AstrBotConfig | None, schema_path: Path) -> dict[str, Any]:
    """Normalize and materialize the plugin config before services are built."""
    raw_or_reset = maybe_reset_to_defaults(
        config or {},
        schema_path,
    )
    raw_config = maybe_materialize_chiyo_preset(
        config if config is not None else raw_or_reset,
        base_config=raw_or_reset,
    )
    return apply_config_preset(raw_config)


class EntrySupportMixin:
    """Thin entry-layer helpers for the Anima plugin shell."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context, config)
        self.config = initialize_plugin_config(
            config,
            Path(__file__).with_name("_conf_schema.json"),
        )
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
        self._generation_verifier = self._services.generation_verifier
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

        verification = await self._generation_verifier.verify_and_maybe_retry(
            event,
            payload,
            user_request=prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            negative_prompt=negative_prompt,
        )
        payload = verification.payload

        message = await self._send_payload(event, payload)
        if payload.get("ok") and not self._last_prompt_summary.get("llm_ok", True):
            await event.send(event.plain_result(
                "（提示词优化这次没走通，是拿你的原文直接画的，可能不太准。要重画就再说一次。）"
            ))
        final = verification.verdict
        if payload.get("ok") and final is not None and not final.passed and not final.skipped:
            issues = "；".join(final.issues[:3]) if final.issues else "和描述有出入"
            await event.send(event.plain_result(
                f"（这张我看着还差点意思：{issues}。要再调整重画就说一声。）"
            ))
        return message

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
