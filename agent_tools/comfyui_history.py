from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time
import uuid
from typing import Any

from comfyui_http import ComfyUIHttpClient


class ComfyUIHistoryRunner:
    """Submit workflows, poll history, and download output images."""

    def __init__(self, config: dict[str, Any], image_outputs: Path):
        self.config = config
        self.image_outputs = Path(image_outputs)
        self.client = ComfyUIHttpClient(config)

    def history(self, prompt_id: str) -> dict[str, Any] | None:
        """Return a prompt history item when ComfyUI has finished it."""
        data = self.client.get_json(f"/history/{prompt_id}", timeout=20)
        item = data.get(prompt_id)
        return item if isinstance(item, dict) else None

    def run_prompt(self, prompt_body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Submit a workflow and wait for its history result."""
        client_id = str(uuid.uuid4())
        submit = self.client.post_json(
            "/prompt",
            {"prompt": prompt_body, "client_id": client_id},
            timeout=20,
        )
        prompt_id = str(submit.get("prompt_id") or "")
        if not prompt_id:
            raise RuntimeError(f"缺少 prompt_id：{submit}")
        timeout = max(1, int(self.config.get("timeout", 300)))
        poll_interval = max(1, int(self.config.get("poll_interval", 2)))
        deadline = time.time() + timeout
        while time.time() < deadline:
            history = self.history(prompt_id)
            if history:
                return prompt_id, history
            time.sleep(poll_interval)
        raise TimeoutError(f"timeout_after_{timeout}s")

    def save_history_images(self, history: dict[str, Any]) -> tuple[list[Path], int]:
        """Download all image outputs from a history payload."""
        images = output_images(history)
        outputs = [self.download_image(image, idx) for idx, image in enumerate(images, start=1)]
        return outputs, len(images)

    def download_image(self, image: dict[str, Any], index: int) -> Path:
        """Download a single ComfyUI output image."""
        self.image_outputs.mkdir(parents=True, exist_ok=True)
        filename = str(image.get("filename") or f"comfyui_{index}.png")
        ext = Path(filename).suffix or ".png"
        output = self.image_outputs / f"{_now()}_comfyui_{index}{ext}"
        output.write_bytes(self.client.view_image_bytes(image, timeout=120))
        return output


def _now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def output_images(history: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract image descriptors from a ComfyUI history payload."""
    images: list[dict[str, Any]] = []
    outputs = history.get("outputs") or {}
    if isinstance(outputs, dict):
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for image in node_output.get("images", []) or []:
                if isinstance(image, dict):
                    images.append(image)
    return images


def history_failed(history: dict[str, Any]) -> dict[str, Any] | None:
    """Return the failed status payload if ComfyUI marked the run failed."""
    status_payload = history.get("status") or {}
    if isinstance(status_payload, dict) and status_payload.get("status_str") not in {None, "success"}:
        return status_payload
    return None
