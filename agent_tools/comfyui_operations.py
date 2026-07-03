from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

from comfyui_history import ComfyUIHistoryRunner, history_failed
from comfyui_http import ComfyUIHttpClient
from comfyui_sizes import generation_size
from comfyui_workflows import (
    anima_img2img_workflow,
    remove_bg_workflow,
    upscale_workflow,
    workflow,
)


def generate_payload(
    config: dict[str, Any],
    defaults: dict[str, Any],
    image_outputs: Path,
    args: Any,
    prompt: str,
) -> dict[str, Any]:
    width = int(args.width or config.get("width", defaults["width"]))
    height = int(args.height or config.get("height", defaults["height"]))
    width, height = generation_size(config, defaults["allowed_sizes"], width, height)
    steps = int(args.steps or config.get("steps", defaults["steps"]))
    cfg = float(args.cfg or config.get("cfg", defaults["cfg"]))
    seed = int(args.seed if args.seed is not None else random.randint(1, 2**32 - 1))
    negative_prompt = str(args.negative_prompt or config.get("negative_prompt", defaults["negative_prompt"]))
    prompt_body = workflow(config, prompt, negative_prompt, width, height, steps, cfg, seed)
    prompt_id, history = _run_prompt(config, image_outputs, prompt_body)
    status_payload = history_failed(history)
    if status_payload:
        return {"ok": False, "error": "workflow_failed", "prompt_id": prompt_id, "status": status_payload}
    outputs, raw_image_count = _save_history_images(config, image_outputs, history)
    return {
        "ok": bool(outputs),
        "operation": "comfyui_generate",
        "prompt_id": prompt_id,
        "seed": seed,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "outputs": [str(path) for path in outputs],
        "raw_image_count": raw_image_count,
        "error": None if outputs else "no image found in history",
    }


def edit_payload(
    config: dict[str, Any],
    image_outputs: Path,
    resolve_image: Callable[[str | None], Path],
    args: Any,
    prompt: str,
) -> dict[str, Any]:
    image = resolve_image(args.input)
    width, height = _image_size(image, int(config.get("max_image_side", 1024)))
    image_name = ComfyUIHttpClient(config).upload_image(image)
    steps = int(args.steps or config.get("steps", 20))
    cfg = float(args.cfg or config.get("cfg", 4.0))
    denoise = float(args.denoise or config.get("edit_denoise", 0.55))
    seed = int(args.seed if args.seed is not None else random.randint(1, 2**32 - 1))
    prompt_body = anima_img2img_workflow(config, prompt, image_name, width, height, steps, cfg, seed, denoise)
    prompt_id, history = _run_prompt(config, image_outputs, prompt_body)
    status_payload = history_failed(history)
    if status_payload:
        return {"ok": False, "error": "workflow_failed", "prompt_id": prompt_id, "status": status_payload}
    outputs, raw_image_count = _save_history_images(config, image_outputs, history)
    return {
        "ok": bool(outputs),
        "operation": "comfyui_edit",
        "prompt_id": prompt_id,
        "input": str(image),
        "uploaded_image": image_name,
        "seed": seed,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "denoise": denoise,
        "outputs": [str(path) for path in outputs],
        "raw_image_count": raw_image_count,
        "error": None if outputs else "no image found in history",
    }


def upscale_payload(
    config: dict[str, Any],
    image_outputs: Path,
    resolve_image: Callable[[str | None], Path],
    args: Any,
) -> dict[str, Any]:
    image = resolve_image(args.input)
    image_name = ComfyUIHttpClient(config).upload_image(image)
    scale = float(args.scale or config.get("upscale_factor", 2.0))
    prompt_body = upscale_workflow(config, image_name, scale)
    prompt_id, history = _run_prompt(config, image_outputs, prompt_body)
    status_payload = history_failed(history)
    if status_payload:
        return {"ok": False, "error": "workflow_failed", "prompt_id": prompt_id, "status": status_payload}
    outputs, raw_image_count = _save_history_images(config, image_outputs, history)
    return {
        "ok": bool(outputs),
        "operation": "comfyui_upscale",
        "prompt_id": prompt_id,
        "input": str(image),
        "uploaded_image": image_name,
        "scale": scale,
        "outputs": [str(path) for path in outputs],
        "raw_image_count": raw_image_count,
        "error": None if outputs else "no image found in history",
    }


def remove_bg_payload(
    config: dict[str, Any],
    image_outputs: Path,
    resolve_image: Callable[[str | None], Path],
    args: Any,
) -> dict[str, Any]:
    image = resolve_image(args.input)
    image_name = ComfyUIHttpClient(config).upload_image(image)
    prompt_body = remove_bg_workflow(config, image_name)
    prompt_id, history = _run_prompt(config, image_outputs, prompt_body)
    status_payload = history_failed(history)
    if status_payload:
        return {"ok": False, "error": "workflow_failed", "prompt_id": prompt_id, "status": status_payload}
    outputs, raw_image_count = _save_history_images(config, image_outputs, history)
    return {
        "ok": bool(outputs),
        "operation": "comfyui_remove_bg",
        "prompt_id": prompt_id,
        "input": str(image),
        "uploaded_image": image_name,
        "outputs": [str(path) for path in outputs],
        "raw_image_count": raw_image_count,
        "error": None if outputs else "no image found in history",
    }


def _run_prompt(config: dict[str, Any], image_outputs: Path, prompt_body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return ComfyUIHistoryRunner(config, image_outputs).run_prompt(prompt_body)


def _save_history_images(config: dict[str, Any], image_outputs: Path, history: dict[str, Any]) -> tuple[list[Path], int]:
    return ComfyUIHistoryRunner(config, image_outputs).save_history_images(history)


def _image_size(path: Path, max_side: int) -> tuple[int, int]:
    image = ImageOps.exif_transpose(Image.open(path))
    width, height = image.size
    if max(width, height) > max_side > 0:
        scale = max_side / max(width, height)
        width = max(8, int(width * scale))
        height = max(8, int(height * scale))
    width = max(64, (width // 8) * 8)
    height = max(64, (height // 8) * 8)
    return width, height
