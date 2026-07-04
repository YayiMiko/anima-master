from __future__ import annotations

from typing import Any

from comfyui_http import ComfyUIHttpClient


def build_status_payload(config: dict[str, Any], allowed_sizes: list[str]) -> dict[str, Any]:
    """Return the JSON payload for the ComfyUI helper status command."""
    payload: dict[str, Any] = {
        "ok": True,
        "base_url": config.get("comfyui_base_url"),
        "workflow": config.get("workflow"),
        "allowed_sizes": allowed_sizes,
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
            }
        )
    except Exception as exc:
        payload.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return payload


def _available_models(object_info: dict[str, Any], node: str, input_name: str) -> list[str]:
    try:
        value = object_info[node]["input"]["required"][input_name]
        if isinstance(value, list) and value and isinstance(value[0], list):
            return [str(item) for item in value[0]]
    except Exception:
        pass
    return []
