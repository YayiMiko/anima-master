from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


class ComfyUIHttpClient:
    """Small HTTP wrapper for ComfyUI API calls used by the CLI helper."""

    def __init__(self, config: dict[str, Any]):
        base = str(config.get("comfyui_base_url") or "").strip()
        if not base:
            raise SystemExit("comfyui_base_url is not configured")
        self.base_url = base.rstrip("/")

    def get_json(self, path: str, timeout: int = 10) -> dict[str, Any]:
        response = requests.get(self.base_url + path, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def post_json(self, path: str, body: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
        response = requests.post(self.base_url + path, json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def upload_image(self, path: Path) -> str:
        with path.open("rb") as handle:
            response = requests.post(
                self.base_url + "/upload/image",
                files={"image": (path.name, handle, "image/png")},
                data={"subfolder": "AstrBot", "type": "input", "overwrite": "true"},
                timeout=120,
            )
        response.raise_for_status()
        payload = response.json()
        name = str(payload.get("name") or path.name)
        subfolder = str(payload.get("subfolder") or "").strip("/")
        return f"{subfolder}/{name}" if subfolder else name

    def view_image_bytes(self, image: dict[str, Any], timeout: int = 120) -> bytes:
        query = urlencode(
            {
                "filename": image.get("filename", ""),
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            }
        )
        response = requests.get(self.base_url + f"/view?{query}", timeout=timeout)
        response.raise_for_status()
        return response.content
