from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp

try:
    from .chat_delivery import (
        ack_timeout_delivery,
        is_ack_timeout,
        no_output_delivery,
        operation_failed_delivery,
        send_failed_delivery,
        sent_delivery,
        skipped_delivery,
    )
    from .comfyui_startup import ComfyUIStartupManager
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from chat_delivery import (
        ack_timeout_delivery,
        is_ack_timeout,
        no_output_delivery,
        operation_failed_delivery,
        send_failed_delivery,
        sent_delivery,
        skipped_delivery,
    )
    from comfyui_startup import ComfyUIStartupManager

try:
    from aiocqhttp.exceptions import ActionFailed
except Exception:  # pragma: no cover - aiocqhttp may be absent in tests.
    ActionFailed = None


class ComfyUIRuntime:
    """Run local ComfyUI helper tools and deliver generated outputs."""

    def __init__(
        self,
        *,
        root: Path,
        tool: Path,
        prompt_tool: Path,
        python: Path,
        config: dict[str, Any],
        logger: Any,
        get_bool: Callable[[str, bool], bool],
        get_int: Callable[[str, int], int],
        get_str: Callable[[str, str], str],
    ):
        """Store runtime dependencies for local helper processes.

        Args:
            root: AstrBot workspace root used as subprocess working directory.
            tool: Main ComfyUI helper script path.
            prompt_tool: Image prompt helper script path.
            python: Preferred Python interpreter path.
            config: Plugin configuration dict.
            logger: Logger compatible with AstrBot logger methods.
            get_bool: Config boolean accessor.
            get_int: Config integer accessor.
            get_str: Config string accessor.
        """
        self.root = root
        self.tool = tool
        self.prompt_tool = prompt_tool
        self.python = python
        self.config = config
        self.logger = logger
        self._bool = get_bool
        self._int = get_int
        self._str = get_str
        self._startup = ComfyUIStartupManager(
            root=self.root,
            config=self.config,
            logger=self.logger,
            get_bool=self._bool,
            get_int=self._int,
            get_str=self._str,
            run_status=lambda: self.run_tool(["status"]),
        )

    async def run_python_tool(
        self, script: Path, args: list[str], timeout: int
    ) -> dict[str, Any]:
        python = str(self.python if self.python.exists() else Path(sys.executable))
        proc = await asyncio.create_subprocess_exec(
            python,
            str(script),
            *args,
            cwd=str(self.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"ok": False, "error": f"local_wait_timeout_after_{timeout}s"}

        out_text = stdout.decode("utf-8", errors="replace").strip()
        err_text = stderr.decode("utf-8", errors="replace").strip()
        if not out_text:
            return {
                "ok": False,
                "error": "empty_tool_output",
                "stderr": err_text[-1200:],
                "returncode": proc.returncode,
            }
        try:
            payload = json.loads(out_text)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "invalid_tool_json",
                "stdout": out_text[-2000:],
                "stderr": err_text[-1200:],
                "returncode": proc.returncode,
            }
        if err_text:
            payload["stderr"] = err_text[-1200:]
        payload["returncode"] = proc.returncode
        return payload

    async def run_tool(self, args: list[str]) -> dict[str, Any]:
        timeout = max(self._int("timeout", 300), 30) + 60
        return await self.run_python_tool(self.tool, args, timeout)

    async def run_prompt_tool(self, args: list[str]) -> dict[str, Any]:
        return await self.run_python_tool(self.prompt_tool, args, 120)

    async def ensure_ready(self, event: Any) -> dict[str, Any]:
        return await self._startup.ensure_ready(event)

    def failure_reason(self, payload: dict[str, Any]) -> str:
        detail = str(payload.get("error") or "unknown_error")
        if detail.startswith(("timeout_after_", "local_wait_timeout_after_")):
            return "ComfyUI 排队或生成过久"
        if detail == "http_error":
            return f"ComfyUI 接口请求失败 HTTP {payload.get('status_code')}"
        if detail == "workflow_failed":
            return "ComfyUI 工作流执行失败"
        if detail == "no image found in history":
            return "ComfyUI 完成了任务但没有产出图片"
        if detail == "comfyui_offline":
            return "ComfyUI 未启动或无法连接。请先启动 ComfyUI，或在插件配置里开启“由 AstrBot 启动 ComfyUI”并填写启动命令"
        if detail == "startup_command_not_configured":
            return "ComfyUI 未启动，且“由 AstrBot 启动 ComfyUI”没有填写启动命令。请先手动启动 ComfyUI，或关闭该开关"
        if detail == "auto_start_not_permitted":
            return "ComfyUI 未启动，且当前用户没有权限让 AstrBot 启动 ComfyUI"
        if detail.startswith("auto_start_timeout_after_"):
            return "已尝试启动 ComfyUI，但等待就绪超时"
        if detail == "no recent image found in workspace inputs":
            return "没有找到最近收到的图片"
        if detail == "reference_image_not_found":
            summary = payload.get("image_input_summary") if isinstance(payload.get("image_input_summary"), dict) else {}
            direct_count = int(summary.get("direct_images") or 0)
            reply_count = int(summary.get("reply_images") or 0)
            raw_count = int(summary.get("raw_images") or 0)
            if direct_count or reply_count or raw_count:
                return (
                    "检测到了图片消息，但没有成功下载/保存参考图。"
                    f"direct={direct_count} reply={reply_count} raw={raw_count}，"
                    "请稍后重试，或引用图片消息再试"
                )
            return "没有拿到参考图。请直接带图发送，或引用一条包含图片的消息再使用 /anm"
        if "unsupported_size" in detail:
            return "尺寸不在当前 Anima 预设范围内"
        return detail[:300]

    async def send_payload(self, event: Any, payload: dict[str, Any]) -> str:
        if self._bool("debug_send_payload_enabled", False):
            self.logger.info(
                "[comfyui_agent] send payload ok=%s outputs=%s error=%s",
                payload.get("ok"),
                payload.get("outputs"),
                payload.get("error"),
            )
        if not payload.get("ok"):
            reason = self.failure_reason(payload)
            message = f"ComfyUI 操作失败：{reason}。"
            payload["delivery"] = operation_failed_delivery(payload, message)
            await event.send(event.plain_result(message))
            return message

        outputs = [str(item) for item in payload.get("outputs", []) if Path(str(item)).exists()]
        if not outputs:
            message = "ComfyUI 完成了任务，但没有拿到可发送的图片。"
            payload["delivery"] = no_output_delivery(message)
            await event.send(event.plain_result(message))
            return "ComfyUI 已完成任务，但没有产出可发送的图片。"

        if self._bool("send_result_to_chat", True):
            for output in outputs[: self._int("max_send_images", 1)]:
                try:
                    await event.send(event.chain_result([Comp.Image.fromFileSystem(output)]))
                except Exception as exc:
                    wording = str(getattr(exc, "wording", "") or getattr(exc, "message", "") or exc)
                    if is_ack_timeout(exc, ActionFailed):
                        self.logger.warning(
                            "[comfyui_agent] image generated but platform send ACK timed out; "
                            "图片可能已经送达。path=%s error=%s",
                            output,
                            wording[:500],
                        )
                        message = "ComfyUI 已生成图片，但聊天平台发送回执超时：" + ", ".join(outputs)
                        payload["delivery"] = ack_timeout_delivery(outputs, output, exc, message)
                        return message
                    self.logger.warning(
                        "[comfyui_agent] image generated but sending failed. path=%s error=%s: %s",
                        output,
                        type(exc).__name__,
                        str(exc)[:500],
                    )
                    message = "ComfyUI 已生成图片，但发送失败：" + ", ".join(outputs)
                    payload["delivery"] = send_failed_delivery(outputs, output, exc, message)
                    return message
            message = "ComfyUI 已生成并发送图片：" + ", ".join(outputs)
            payload["delivery"] = sent_delivery(outputs, message)
            return message
        message = "ComfyUI 已生成并发送图片：" + ", ".join(outputs)
        payload["delivery"] = skipped_delivery(outputs, message)
        return message
