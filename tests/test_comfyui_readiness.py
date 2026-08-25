from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = PLUGIN_DIR / "agent_tools"
for path in (PLUGIN_DIR, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import comfyui_agent  # noqa: E402
import comfyui_startup  # noqa: E402
import comfyui_status  # noqa: E402


class _Logger:
    def info(self, *args: object) -> None:
        pass

    def warning(self, *args: object) -> None:
        pass


class _Event:
    def get_sender_id(self) -> str:
        return "1"

    def is_admin(self) -> bool:
        return True


def _manager(
    tmp_path: Path,
    statuses: list[dict[str, object]],
    health: AsyncMock | None = None,
) -> comfyui_startup.ComfyUIStartupManager:
    config = {
        "auto_start": True,
        "readiness_cache_seconds": 300,
        "readiness_retry_delay_seconds": 0,
    }
    run_status = AsyncMock(side_effect=statuses)
    manager = comfyui_startup.ComfyUIStartupManager(
        root=tmp_path,
        config=config,
        logger=_Logger(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        run_status=run_status,
        run_health=health,
    )
    manager._test_run_status = run_status
    return manager


def test_status_uses_targeted_object_info_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    paths: list[str] = []
    config = {
        "comfyui_base_url": "http://127.0.0.1:8188",
        "unet_name": "anima.safetensors",
        "clip_name": "clip.safetensors",
        "vae_name": "vae.safetensors",
    }

    class _Client:
        def __init__(self, client_config: dict[str, object]) -> None:
            assert client_config is config

        def get_json(self, path: str, timeout: int = 10) -> dict[str, object]:
            paths.append(path)
            if path == "/system_stats":
                return {"system": {}, "devices": []}
            node_name = path.rsplit("/", 1)[-1]
            payload: dict[str, object] = {node_name: {}}
            model_fields = {
                "UNETLoader": ("unet_name", "anima.safetensors"),
                "CLIPLoader": ("clip_name", "clip.safetensors"),
                "VAELoader": ("vae_name", "vae.safetensors"),
            }
            if node_name in model_fields:
                field, value = model_fields[node_name]
                payload[node_name] = {
                    "input": {"required": {field: [[value]]}},
                }
            return payload

    monkeypatch.setattr(comfyui_status, "ComfyUIHttpClient", _Client)
    monkeypatch.setattr(comfyui_status.socket, "getaddrinfo", lambda *args: [])

    payload = comfyui_status.build_status_payload(config, ["1024x1536"])

    assert payload["ok"] is True
    assert payload["unet_available"] is True
    assert payload["clip_available"] is True
    assert payload["vae_available"] is True
    assert "/object_info" not in paths
    assert {f"/object_info/{name}" for name in comfyui_status.CAPABILITY_NODE_NAMES} <= set(paths)


def test_quick_status_skips_capability_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    paths: list[str] = []

    class _Client:
        def __init__(self, config: dict[str, object]) -> None:
            pass

        def get_json(self, path: str, timeout: int = 10) -> dict[str, object]:
            paths.append(path)
            return {"system": {}, "devices": []}

    monkeypatch.setattr(comfyui_status, "ComfyUIHttpClient", _Client)
    monkeypatch.setattr(comfyui_status.socket, "getaddrinfo", lambda *args: [])

    payload = comfyui_status.build_status_payload(
        {"comfyui_base_url": "http://127.0.0.1:8188"},
        [],
        include_capabilities=False,
    )

    assert paths == ["/system_stats"]
    assert payload["comfyui_api_reachable"] is True
    assert payload["capabilities_checked"] is False


@pytest.mark.asyncio
async def test_recent_validation_uses_lightweight_health_probe(tmp_path: Path) -> None:
    ready = {
        "ok": True,
        "comfyui_api_reachable": True,
        "unet_available": True,
        "clip_available": True,
        "vae_available": True,
    }
    health = AsyncMock(return_value={"ok": True, "comfyui_api_reachable": True})
    manager = _manager(tmp_path, [ready], health)

    assert (await manager.ensure_ready(_Event()))["ok"] is True
    second = await manager.ensure_ready(_Event())

    assert second["ok"] is True
    assert second["status"]["readiness_source"] == "recent_validated_cache"
    assert manager._test_run_status.await_count == 1
    assert health.await_count == 1


@pytest.mark.asyncio
async def test_reachable_api_failure_does_not_start_another_process(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        [
            {
                "ok": False,
                "comfyui_api_reachable": True,
                "unet_available": False,
            }
        ],
    )
    manager.start_comfyui_process = AsyncMock(return_value={"ok": True})

    result = await manager.ensure_ready(_Event())

    assert result["error"] == "comfyui_capability_check_failed"
    manager.start_comfyui_process.assert_not_awaited()


@pytest.mark.asyncio
async def test_windows_executable_starts_without_outer_shell_quotes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "ComfyUI.exe"
    executable.touch()
    config = {
        "startup_command": str(executable),
        "startup_workdir": str(tmp_path),
        "startup_visible_window": True,
    }
    create_process = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(comfyui_startup.sys, "platform", "win32")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    manager = comfyui_startup.ComfyUIStartupManager(
        root=tmp_path,
        config=config,
        logger=_Logger(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        run_status=AsyncMock(),
    )

    result = await manager.start_comfyui_process()

    assert result["ok"] is True
    assert create_process.await_args.args == (str(executable),)


def test_astrbot_root_detection_accepts_uv_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "data" / "config").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert comfyui_agent._find_astrbot_root() == tmp_path
