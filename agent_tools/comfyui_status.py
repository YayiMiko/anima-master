from __future__ import annotations

import platform
import socket
from typing import Any
from urllib.parse import urlparse

import requests

from comfyui_http import ComfyUIHttpClient


def _connection_issue(error: Exception, mode: str) -> tuple[str, str]:
    """Classify a ComfyUI connection error.

    Args:
        error: Exception raised while reaching ComfyUI.
        mode: Connection mode, such as `remote` or `same-machine`.

    Returns:
        A stable issue code and a user-facing hint.
    """
    text = str(error)
    if isinstance(error, requests.exceptions.ConnectTimeout):
        if mode == "remote":
            return (
                "remote_connect_timeout",
                "服务器连不到 ComfyUI。若本机 127.0.0.1 可打开，请用 --listen 0.0.0.0 重启 ComfyUI，并确认 Windows 防火墙和 Tailscale 在线。",
            )
        return "local_connect_timeout", "ComfyUI 连接超时。请确认 ComfyUI 已启动并监听 8188。"
    if isinstance(error, requests.exceptions.ReadTimeout):
        return "api_read_timeout", "ComfyUI API 响应过慢。可能正在启动、卡住或负载过高。"
    if isinstance(error, requests.exceptions.ConnectionError):
        if "Connection refused" in text or "actively refused" in text:
            return "connection_refused", "目标地址可达但端口拒绝连接。请确认 ComfyUI 已启动并监听配置的端口。"
        if mode == "remote":
            return (
                "remote_connection_failed",
                "服务器无法连接远程 ComfyUI。请确认 ComfyUI 使用 --listen 0.0.0.0 启动，Windows 防火墙允许 8188，Tailscale 在线。",
            )
        return "connection_failed", "无法连接 ComfyUI。请确认地址、端口和进程状态。"
    if isinstance(error, requests.exceptions.HTTPError):
        return "http_error", "ComfyUI 返回 HTTP 错误。请确认地址指向 ComfyUI API，而不是启动器页面。"
    return "unknown_connection_error", "ComfyUI 连接检查失败。请查看日志中的具体错误。"


def build_status_payload(config: dict[str, Any], allowed_sizes: list[str]) -> dict[str, Any]:
    """Return the JSON payload for the ComfyUI helper status command."""
    base_url = str(config.get("comfyui_base_url") or "").strip()
    parsed_base_url = urlparse(base_url)
    comfyui_host = parsed_base_url.hostname or ""
    local_hosts = {"", "127.0.0.1", "localhost", "::1", "0.0.0.0"}
    connection_mode = "same-machine" if comfyui_host in local_hosts else "remote"
    dns_checks: dict[str, bool] = {}
    for host in ("api.deepseek.com", "api.siliconflow.cn", "gchat.qpic.cn"):
        try:
            socket.getaddrinfo(host, 443)
            dns_checks[host] = True
        except Exception:
            dns_checks[host] = False
    payload: dict[str, Any] = {
        "ok": True,
        "base_url": base_url,
        "workflow": config.get("workflow"),
        "allowed_sizes": allowed_sizes,
        "runtime_platform": platform.system() or "unknown",
        "comfyui_connection_mode": connection_mode,
        "comfyui_api_reachable": False,
        "connection_issue": "",
        "connection_hint": "",
        "dns_checks": dns_checks,
    }
    try:
        client = ComfyUIHttpClient(config)
        stats = client.get_json("/system_stats", timeout=10)
        object_info = client.get_json("/object_info", timeout=20)
        devices = stats.get("devices", []) if isinstance(stats, dict) else []
        device = devices[0] if devices else {}
        payload.update(
            {
                "comfyui_version": (stats.get("system") or {}).get("comfyui_version"),
                "gpu": device.get("name"),
                "vram_total_mb": int(device.get("vram_total", 0) / 1024 / 1024),
                "vram_free_mb": int(device.get("vram_free", 0) / 1024 / 1024),
                "unet_available": config.get("unet_name") in _available_models(object_info, "UNETLoader", "unet_name"),
                "clip_available": config.get("clip_name") in _available_models(object_info, "CLIPLoader", "clip_name"),
                "vae_available": config.get("vae_name") in _available_models(object_info, "VAELoader", "vae_name"),
                "img2img_available": all(name in object_info for name in ["LoadImage", "VAEEncode", "ImageScale"]),
                "upscale_available": "ImageScaleBy" in object_info,
                "remove_bg_available": "BiRefNetRMBG" in object_info,
                "comfyui_api_reachable": True,
            }
        )
    except Exception as exc:
        issue, hint = _connection_issue(exc, connection_mode)
        payload.update(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "comfyui_api_reachable": False,
                "connection_issue": issue,
                "connection_hint": hint,
            }
        )
    return payload


def _available_models(object_info: dict[str, Any], node: str, input_name: str) -> list[str]:
    try:
        value = object_info[node]["input"]["required"][input_name]
        if isinstance(value, list) and value and isinstance(value[0], list):
            return [str(item) for item in value[0]]
    except Exception:
        pass
    return []
