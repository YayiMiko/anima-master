from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
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
        run_health: Callable[[], Awaitable[dict[str, Any]]] | None = None,
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
            run_health: Optional lightweight API health callback.
        """
        self.root = Path(root)
        self.config = config
        self.logger = logger
        self._bool = get_bool
        self._int = get_int
        self._str = get_str
        self._run_status = run_status
        self._run_health = run_health or run_status
        self._lock = asyncio.Lock()
        self._last_ready_status: dict[str, Any] = {}
        self._last_ready_at = 0.0

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

    def _remember_ready(self, status: dict[str, Any]) -> None:
        """Cache one fully validated capability result.

        Args:
            status: Successful full ComfyUI status payload.
        """
        self._last_ready_status = dict(status)
        self._last_ready_at = time.monotonic()

    def _cached_ready_status(self) -> dict[str, Any] | None:
        """Return a recent capability result when it remains valid.

        Returns:
            Cached status with age metadata, or ``None`` when expired.
        """
        max_age = max(0, self._int("readiness_cache_seconds", 300))
        age = time.monotonic() - self._last_ready_at
        if not self._last_ready_status or max_age <= 0 or age > max_age:
            return None
        cached = dict(self._last_ready_status)
        cached["readiness_source"] = "recent_validated_cache"
        cached["readiness_cache_age_seconds"] = round(age, 1)
        return cached

    @staticmethod
    def _is_transient_api_timeout(status: dict[str, Any]) -> bool:
        """Return whether a status failure is a temporary API read timeout.

        Args:
            status: ComfyUI status payload.

        Returns:
            Whether the failure can be retried without launching a new process.
        """
        return str(status.get("connection_issue") or "") == "api_read_timeout"

    async def _check_ready(self) -> tuple[bool, dict[str, Any]]:
        """Validate capabilities once, then use a lightweight health probe.

        Returns:
            Readiness flag and the status payload that produced it.
        """
        cached = self._cached_ready_status()
        if cached:
            health = await self._run_health()
            if health.get("comfyui_api_reachable"):
                cached["comfyui_api_reachable"] = True
                cached["health_check"] = "ok"
                return True, cached
            if not self._is_transient_api_timeout(health):
                return False, health

        status = await self._run_status()
        if self.is_ready(status):
            self._remember_ready(status)
            return True, status
        if not self._is_transient_api_timeout(status):
            return False, status

        retry_delay = max(0, self._int("readiness_retry_delay_seconds", 2))
        if retry_delay:
            await asyncio.sleep(retry_delay)
        status = await self._run_status()
        if self.is_ready(status):
            self._remember_ready(status)
            return True, status
        if self._is_transient_api_timeout(status):
            cached = self._cached_ready_status()
            if cached:
                self.logger.warning(
                    "[comfyui_agent] capability check timed out; using recent validation"
                )
                return True, cached
        return False, status

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
            if sys.platform == "win32":
                command_path = Path(command.strip('"'))
                if command_path.suffix.lower() == ".exe" and command_path.exists():
                    await asyncio.create_subprocess_exec(
                        str(command_path),
                        cwd=workdir or str(self.root),
                        stdout=None if visible_window else subprocess.DEVNULL,
                        stderr=None if visible_window else subprocess.DEVNULL,
                        env=env,
                        creationflags=flags,
                    )
                else:
                    shell_command = command
                    if (
                        command_path.suffix.lower() in {".bat", ".cmd"}
                        and command_path.exists()
                    ):
                        shell_command = f'call "{command_path}"'
                    if visible_window:
                        shell_command = (
                            "title AstrBot ComfyUI && chcp 65001 >nul && "
                            + shell_command
                        )
                    await asyncio.create_subprocess_exec(
                        "cmd.exe",
                        "/d",
                        "/k" if visible_window else "/c",
                        shell_command,
                        cwd=workdir or str(self.root),
                        stdout=None if visible_window else subprocess.DEVNULL,
                        stderr=None if visible_window else subprocess.DEVNULL,
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
        ready, status = await self._check_ready()
        if ready:
            return {"ok": True, "status": status}
        if status.get("comfyui_api_reachable"):
            return {
                "ok": False,
                "error": "comfyui_capability_check_failed",
                "status": status,
            }
        if not self._bool("auto_start", False):
            return {"ok": False, "error": "comfyui_offline", "status": status}
        if not self.is_auto_start_allowed(event):
            return {"ok": False, "error": "auto_start_not_permitted", "status": status}

        async with self._lock:
            ready, status = await self._check_ready()
            if ready:
                return {"ok": True, "status": status}
            if status.get("comfyui_api_reachable"):
                return {
                    "ok": False,
                    "error": "comfyui_capability_check_failed",
                    "status": status,
                }

            launched = await self.start_comfyui_process()
            if not launched.get("ok"):
                return launched

            wait_seconds = max(5, self._int("startup_wait_seconds", 120))
            poll_interval = max(1, self._int("startup_poll_interval", 3))
            deadline = asyncio.get_running_loop().time() + wait_seconds
            last_status: dict[str, Any] = {}
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(poll_interval)
                ready, last_status = await self._check_ready()
                if ready:
                    self.logger.info("[comfyui_agent] auto_start ready")
                    return {"ok": True, "status": last_status}
            return {
                "ok": False,
                "error": f"auto_start_timeout_after_{wait_seconds}s",
                "status": last_status,
            }
