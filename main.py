import sys

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr

try:
    from .command_router import parse_hard_route
    from .entry_support import EntrySupportMixin
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from command_router import parse_hard_route
    from entry_support import EntrySupportMixin


class ComfyUIAgentPlugin(EntrySupportMixin, Star):
    """Basic local ComfyUI backend for AstrBot."""

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
