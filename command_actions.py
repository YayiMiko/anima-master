from __future__ import annotations

from typing import Any, Callable

try:
    from .command_router import help_text
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from command_router import help_text


class CommandActionHandler:
    """Dispatch chat commands to Anima plugin actions."""

    def __init__(
        self,
        *,
        config: dict[str, Any],
        task_recorder: Any,
        reference_context: Any,
        is_allowed: Callable[[Any], bool],
        run_tool: Callable[[list[str]], Any],
        ensure_ready: Callable[[Any], Any],
        send_payload: Callable[[Any, dict[str, Any]], Any],
        generate: Callable[..., Any],
        event_image_input: Callable[[Any], Any],
        build_prompt: Callable[..., Any],
        format_spell_payload: Callable[[dict[str, Any]], str],
        get_bool: Callable[[str, bool], bool],
        shorten: Callable[[str, int], str],
    ):
        """Store dependencies for command-side action handling.

        Args:
            config: Plugin configuration dict.
            task_recorder: Task recorder used for debug status output.
            reference_context: Reference-context builder for spell/reverse.
            is_allowed: Permission checker.
            run_tool: Main ComfyUI helper runner.
            ensure_ready: ComfyUI readiness checker.
            send_payload: Chat payload sender.
            generate: Text-to-image generator.
            event_image_input: Image input resolver.
            build_prompt: Prompt builder for img2img.
            format_spell_payload: Spell payload formatter.
            get_bool: Config boolean accessor.
            shorten: Text-shortening helper.
        """
        self.config = config
        self._task_recorder = task_recorder
        self._reference_context = reference_context
        self._is_allowed = is_allowed
        self._run_tool = run_tool
        self._ensure_ready = ensure_ready
        self._send_payload = send_payload
        self._generate = generate
        self._event_image_input = event_image_input
        self._build_prompt = build_prompt
        self._format_spell_payload = format_spell_payload
        self._bool = get_bool
        self._shorten = shorten

    def status_text(self, payload: dict[str, Any]) -> str:
        """Render a chat-visible ComfyUI status response.

        Args:
            payload: Status payload returned by the ComfyUI helper.

        Returns:
            Human-readable status text.
        """
        if not payload.get("ok"):
            return f"ComfyUI 状态检查失败：{payload.get('error')}"
        lines = [
            "ComfyUI agent 状态：",
            f"- 启用：{payload.get('enabled')}",
            f"- 地址：{payload.get('base_url')}",
            f"- 工作流：{payload.get('workflow')}",
            f"- 尺寸预设：{', '.join(payload.get('allowed_sizes') or [])}",
            f"- ComfyUI：{payload.get('comfyui_version')}",
            f"- GPU：{payload.get('gpu')}",
            f"- 显存：{payload.get('vram_free_mb')} / {payload.get('vram_total_mb')} MB",
            f"- UNET 可用：{payload.get('unet_available')}",
            f"- CLIP 可用：{payload.get('clip_available')}",
            f"- VAE 可用：{payload.get('vae_available')}",
        ]
        return "\n".join(lines)

    async def edit(self, event: Any, prompt: str) -> str:
        if not self._bool("img2img_enabled", False):
            return "图生图/改图功能已关闭。当前先保留文生图、法术解析和图片反推主线。"
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        ready = await self._ensure_ready(event)
        if not ready.get("ok"):
            return await self._send_payload(event, ready)
        prompt = str(prompt or "").strip()
        if not prompt:
            return "Missing ComfyUI edit prompt."
        image_input = await self._event_image_input(event)
        if self._bool("prompt_optimize_img2img_enabled", True):
            prompt = await self._build_prompt(event, prompt, mode="img2img")
        payload = await self._run_tool(["edit", "--prompt", prompt, "--input", image_input or "latest"])
        return await self._send_payload(event, payload)

    async def spell(self, event: Any) -> str:
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        payload = await self._reference_context.image_spell_payload(event)
        return self._format_spell_payload(payload)

    async def reverse(self, event: Any) -> str:
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        image_input = await self._event_image_input(event)
        tags = await self._reference_context.reverse_image_tags(event, image_input)
        if not tags:
            return "图片反推失败：没有可用图片或视觉模型调用失败。"
        return "图片反推 tags：\n" + self._shorten(tags, 2200)

    async def upscale(self, event: Any) -> str:
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        ready = await self._ensure_ready(event)
        if not ready.get("ok"):
            return await self._send_payload(event, ready)
        image_input = await self._event_image_input(event)
        payload = await self._run_tool(["upscale", "--input", image_input or "latest"])
        return await self._send_payload(event, payload)

    async def remove_bg(self, event: Any) -> str:
        return "去背景功能暂未开放。当前先保留文生图、法术解析和图片反推主线。"

    async def handle_action(self, event: Any, action: str, prompt: str) -> str | None:
        """Handle one parsed command action.

        Args:
            event: AstrBot message event.
            action: Parsed action key from `command_router`.
            prompt: Prompt text after the action keyword.

        Returns:
            Optional message to send back. Generation returns None because it
            sends image results directly.
        """
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        if action == "help":
            return help_text(self._bool("img2img_enabled", False))
        if action == "status":
            return self.status_text(await self._run_tool(["status"]))
        if action == "debug_status":
            return self._task_recorder.debug_status_text(self.config)
        if action == "generate":
            if not prompt:
                return "请在后面写完整 prompt 或 tags。"
            await self._generate(event, prompt)
            return None
        if action == "edit":
            if not prompt:
                return "请在后面写改图 prompt。"
            return await self.edit(event, prompt)
        if action == "disabled_upscale":
            return "放大功能已关闭。"
        if action == "disabled_remove_bg":
            return await self.remove_bg(event)
        if action == "spell":
            return await self.spell(event)
        if action == "reverse":
            return await self.reverse(event)
        return "未知 Anima 指令。"
