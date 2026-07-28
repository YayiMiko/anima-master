from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any


class ComfyUIStartupManager:
    """Manage same-machine ComfyUI auto-start behavior."""

    def __init__(
        self,
        *,
        root: Path,
        config: dict[str, Any],
        logger: Any,
        get_bool: Callable[[str, bool], bool],
        get_int: Callable[[str, int], int],
        get_str: Callable[[str, str], str],
        run_status: Callable[[], Awaitable[dict[str, Any]]],
    ):
        """Store dependencies for ComfyUI auto-start checks.

        Args:
            root: AstrBot runtime root used as the default startup workdir.
            config: Plugin configuration dict.
            logger: Logger compatible with AstrBot logger methods.
            get_bool: Config boolean accessor.
            get_int: Config integer accessor.
            get_str: Config string accessor.
            run_status: Async callback returning the ComfyUI status payload.
        """
        self.root = Path(root)
        self.config = config
        self.logger = logger
        self._bool = get_bool
        self._int = get_int
        self._str = get_str
        self._run_status = run_status
        self._lock = asyncio.Lock()

    def is_auto_start_allowed(self, event: Any) -> bool:
        """Return whether the sender may trigger same-machine auto-start.

        Args:
            event: AstrBot message event.

        Returns:
            True when auto-start is enabled and the sender is allowed.
        """
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
        """Return whether ComfyUI status satisfies generation requirements.

        Args:
            payload: Status payload returned by the helper.

        Returns:
            True when ComfyUI and required model files are available.
        """
        return bool(
            payload.get("ok")
            and payload.get("unet_available")
            and payload.get("clip_available")
            and payload.get("vae_available")
        )

    async def start_comfyui_process(self) -> dict[str, Any]:
        """Start ComfyUI on the same machine as AstrBot.

        Returns:
            A status payload indicating whether the process launch was started.
        """
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
                if (
                    command_path.suffix.lower() in {".bat", ".cmd"}
                    and command_path.exists()
                ):
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
            return {
                "ok": False,
                "error": f"startup_failed: {type(exc).__name__}: {exc}",
            }
        self.logger.info(
            "[comfyui_agent] auto_start launched command=%s workdir=%s visible_window=%s",
            command,
            workdir or str(self.root),
            visible_window,
        )
        return {"ok": True}

    async def ensure_ready(self, event: Any) -> dict[str, Any]:
        """Ensure ComfyUI is ready, optionally launching it on the same machine.

        Args:
            event: AstrBot message event.

        Returns:
            Readiness payload used by generation tasks.
        """
        status = await self._run_status()
        if self.is_ready(status):
            return {"ok": True, "status": status}
        if not self._bool("auto_start", False):
            return {"ok": False, "error": "comfyui_offline", "status": status}
        if not self.is_auto_start_allowed(event):
            return {"ok": False, "error": "auto_start_not_permitted", "status": status}

        async with self._lock:
            status = await self._run_status()
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
                last_status = await self._run_status()
                if self.is_ready(last_status):
                    self.logger.info("[comfyui_agent] auto_start ready")
                    return {"ok": True, "status": last_status}
            return {
                "ok": False,
                "error": f"auto_start_timeout_after_{wait_seconds}s",
                "status": last_status,
            }
