from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

import astrbot.api.message_components as Comp

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
        self._startup_lock = asyncio.Lock()

    def is_auto_start_allowed(self, event: Any) -> bool:
        if not self._bool("auto_start", False):
            return False
        allowed = self.config.get("auto_start_allowed_sender_ids", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        allowed_set = {str(item).strip() for item in allowed or [] if str(item).strip()}
        if str(event.get_sender_id()) in allowed_set:
            return True
        if self._bool("auto_start_admin_only", True):
            return event.is_admin()
        return True

    def is_ready(self, payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("ok")
            and payload.get("enabled", True)
            and payload.get("unet_available")
            and payload.get("clip_available")
            and payload.get("vae_available")
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
        timeout = max(self._int("timeout", 900), 30) + 60
        return await self.run_python_tool(self.tool, args, timeout)

    async def run_prompt_tool(self, args: list[str]) -> dict[str, Any]:
        return await self.run_python_tool(self.prompt_tool, args, 120)

    async def start_comfyui_process(self) -> dict[str, Any]:
        command = self._str("startup_command", "").strip()
        workdir = self._str("startup_workdir", "").strip()
        visible_window = self._bool("startup_visible_window", True)
        if not command:
            return {"ok": False, "error": "startup_command_not_configured"}
        if workdir and not Path(workdir).exists():
            return {"ok": False, "error": f"startup_workdir_not_found: {workdir}"}
        flags = 0
        if sys.platform == "win32" and not visible_window:
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        elif sys.platform == "win32":
            flags |= getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("TQDM_DISABLE", "1")
        try:
            if sys.platform == "win32" and visible_window:
                command_path = Path(command.strip('"'))
                if command_path.suffix.lower() in {".bat", ".cmd"} and command_path.exists():
                    cmd_args = [
                        "cmd.exe",
                        "/k",
                        "call",
                        str(command_path),
                    ]
                else:
                    cmd_args = [
                        "cmd.exe",
                        "/s",
                        "/k",
                        f'"title AstrBot ComfyUI && chcp 65001 >nul && {command}"',
                    ]
                await asyncio.create_subprocess_exec(
                    *cmd_args,
                    cwd=workdir or str(self.root),
                    env=env,
                    creationflags=flags,
                )
            else:
                await asyncio.create_subprocess_shell(
                    command,
                    cwd=workdir or str(self.root),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                    creationflags=flags,
                )
        except Exception as exc:
            return {"ok": False, "error": f"startup_failed: {type(exc).__name__}: {exc}"}
        self.logger.info(
            "[comfyui_agent] auto_start launched command=%s workdir=%s visible_window=%s",
            command,
            workdir or str(self.root),
            visible_window,
        )
        return {"ok": True}

    async def ensure_ready(self, event: Any) -> dict[str, Any]:
        status = await self.run_tool(["status"])
        if self.is_ready(status):
            return {"ok": True, "status": status}
        if not self._bool("auto_start", False):
            return {"ok": False, "error": "comfyui_offline", "status": status}
        if not self.is_auto_start_allowed(event):
            return {"ok": False, "error": "auto_start_not_permitted", "status": status}

        async with self._startup_lock:
            status = await self.run_tool(["status"])
            if self.is_ready(status):
                return {"ok": True, "status": status}

            launched = await self.start_comfyui_process()
            if not launched.get("ok"):
                return launched

            wait_seconds = max(5, self._int("startup_wait_seconds", 120))
            poll_interval = max(1, self._int("startup_poll_interval", 3))
            deadline = asyncio.get_running_loop().time() + wait_seconds
            last_status: dict[str, Any] = {}
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(poll_interval)
                last_status = await self.run_tool(["status"])
                if self.is_ready(last_status):
                    self.logger.info("[comfyui_agent] auto_start ready")
                    return {"ok": True, "status": last_status}
            return {
                "ok": False,
                "error": f"auto_start_timeout_after_{wait_seconds}s",
                "status": last_status,
            }

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
        if detail == "no recent image found in workspace inputs":
            return "没有找到最近收到的图片"
        if detail == "reference_image_not_found":
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
            await event.send(event.plain_result(f"ComfyUI 操作失败：{reason}。"))
            return f"ComfyUI 操作失败：{reason}。"

        outputs = [str(item) for item in payload.get("outputs", []) if Path(str(item)).exists()]
        if not outputs:
            await event.send(event.plain_result("ComfyUI 完成了任务，但没有拿到可发送的图片。"))
            return "ComfyUI operation finished with no output image."

        if self._bool("send_result_to_chat", True):
            for output in outputs[: self._int("max_send_images", 1)]:
                try:
                    await event.send(event.chain_result([Comp.Image.fromFileSystem(output)]))
                except Exception as exc:
                    is_action_failed = ActionFailed is not None and isinstance(exc, ActionFailed)
                    retcode = getattr(exc, "retcode", None)
                    wording = str(getattr(exc, "wording", "") or getattr(exc, "message", "") or exc)
                    if is_action_failed and (retcode == 1200 or "Timeout" in wording):
                        self.logger.warning(
                            "[comfyui_agent] image generated but platform send ACK timed out; "
                            "图片可能已经送达。path=%s error=%s",
                            output,
                            wording[:500],
                        )
                        return "ComfyUI 已生成图片，但聊天平台发送回执超时：" + ", ".join(outputs)
                    self.logger.warning(
                        "[comfyui_agent] image generated but sending failed. path=%s error=%s: %s",
                        output,
                        type(exc).__name__,
                        str(exc)[:500],
                    )
                    return "ComfyUI 已生成图片，但发送失败：" + ", ".join(outputs)
        return "ComfyUI 已生成并发送图片：" + ", ".join(outputs)
