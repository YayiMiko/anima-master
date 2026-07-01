import argparse
import json
import random
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from PIL import Image, ImageOps

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _find_astrbot_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "data").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = _find_astrbot_root()
WORKSPACE = ROOT / "workspace"
INPUTS = WORKSPACE / "inputs"
OUTPUTS = WORKSPACE / "outputs"
IMAGE_OUTPUTS = OUTPUTS / "images"
MANIFEST = INPUTS / "manifest.jsonl"
LATEST_INPUT = INPUTS / "latest.json"
CONFIG = ROOT / "data" / "config" / "astrbot_plugin_anima_master_config.json"
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


DEFAULT_CONFIG = {
    "enabled": True,
    "comfyui_base_url": "http://127.0.0.1:8188",
    "workflow": "anima_t2i",
    "timeout": 900,
    "poll_interval": 2,
    "width": 832,
    "height": 1216,
    "allowed_sizes": ["832x1216", "896x1152", "1024x1024", "1152x896", "1216x832", "768x1344", "1344x768"],
    "steps": 30,
    "cfg": 5.0,
    "sampler_name": "er_sde",
    "scheduler": "beta57",
    "unet_name": "anima_baseV10.safetensors",
    "clip_name": "qwen_3_06b_base.safetensors",
    "vae_name": "qwen_image_vae.safetensors",
    "negative_prompt": "worst quality, low quality, artist name",
    "edit_denoise": 0.55,
    "max_image_side": 1024,
    "upscale_factor": 2.0,
    "remove_bg_model": "BiRefNet_lite",
}


def _parse_size(value: Any) -> tuple[int, int] | None:
    if isinstance(value, str) and "x" in value.lower():
        left, right = value.lower().split("x", 1)
        try:
            width = int(left.strip())
            height = int(right.strip())
        except ValueError:
            return None
        if width > 0 and height > 0:
            return width, height
    if isinstance(value, dict):
        try:
            width = int(value.get("width"))
            height = int(value.get("height"))
        except (TypeError, ValueError):
            return None
        if width > 0 and height > 0:
            return width, height
    return None


def _allowed_sizes(config: dict[str, Any]) -> list[tuple[int, int]]:
    raw_sizes = config.get("allowed_sizes") or DEFAULT_CONFIG["allowed_sizes"]
    sizes: list[tuple[int, int]] = []
    for item in raw_sizes if isinstance(raw_sizes, list) else []:
        parsed = _parse_size(item)
        if parsed and parsed not in sizes:
            sizes.append(parsed)
    if not sizes:
        sizes = [item for item in (_parse_size(item) for item in DEFAULT_CONFIG["allowed_sizes"]) if item]
    return sizes


def _generation_size(config: dict[str, Any], width: int, height: int) -> tuple[int, int]:
    width = int(width)
    height = int(height)
    allowed = _allowed_sizes(config)
    if allowed and (width, height) not in allowed:
        requested_ratio = width / height
        same_orientation = [
            size
            for size in allowed
            if (size[0] >= size[1]) == (width >= height)
        ] or allowed
        width, height = min(
            same_orientation,
            key=lambda size: (abs((size[0] / size[1]) - requested_ratio), abs(size[0] * size[1] - width * height)),
        )
    return width, height

def _now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _safe_stem(text: str, fallback: str = "comfyui") -> str:
    keep = []
    for ch in str(text):
        if ch.isalnum() or ch in "-_":
            keep.append(ch)
        elif ch in " .":
            keep.append("_")
    value = "".join(keep).strip("._-")
    return value[:50] or fallback


def _json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    config.update(_json_file(CONFIG))
    return config


def _inside_workspace(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(WORKSPACE.resolve())
    except ValueError:
        raise SystemExit(f"path is outside workspace: {path}")
    return resolved


def _manifest_records() -> list[dict[str, Any]]:
    if not MANIFEST.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("kind") == "image":
            records.append(item)
    return records


def _path_from_record(record: dict[str, Any]) -> Path | None:
    value = record.get("path") or record.get("relative_path")
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = WORKSPACE / path
    try:
        path = _inside_workspace(path)
    except SystemExit:
        return None
    if path.exists() and path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
        return path
    return None


def _recent_images(limit: int) -> list[Path]:
    records = list(reversed(_manifest_records()))
    images: list[Path] = []
    seen: set[Path] = set()
    for record in records:
        path = _path_from_record(record)
        if not path or path in seen:
            continue
        images.append(path)
        seen.add(path)
        if len(images) >= limit:
            break
    if images:
        return images
    candidates = [
        p
        for p in INPUTS.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[:limit]


def _latest_image() -> Path:
    latest = _json_file(LATEST_INPUT)
    path = _path_from_record(latest)
    if path:
        return path
    recent = _recent_images(1)
    if recent:
        return recent[0]
    raise SystemExit("no recent image found in workspace inputs")


def resolve_image(value: str | None) -> Path:
    value = str(value or "latest").strip()
    if not value or value.lower() == "latest":
        return _latest_image()
    if value.lower().startswith("recent:"):
        try:
            index = max(1, int(value.split(":", 1)[1]))
        except ValueError:
            index = 1
        recent = _recent_images(index)
        if len(recent) >= index:
            return recent[index - 1]
        raise SystemExit("recent image not found")
    path = Path(value)
    if not path.is_absolute():
        path = WORKSPACE / path
    path = _inside_workspace(path)
    if not path.exists() or not path.is_file():
        raise SystemExit(f"input image not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise SystemExit(f"unsupported input image type: {path.suffix}")
    return path


def _base_url(config: dict[str, Any]) -> str:
    base = str(config.get("comfyui_base_url") or "").strip()
    if not base:
        raise SystemExit("comfyui_base_url is not configured")
    return base.rstrip("/")


def _get_json(config: dict[str, Any], path: str, timeout: int = 10) -> dict[str, Any]:
    response = requests.get(_base_url(config) + path, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _post_json(config: dict[str, Any], path: str, body: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    response = requests.post(_base_url(config) + path, json=body, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _upload_image(config: dict[str, Any], path: Path) -> str:
    with path.open("rb") as handle:
        response = requests.post(
            _base_url(config) + "/upload/image",
            files={"image": (path.name, handle, "image/png")},
            data={"subfolder": "AstrBot", "type": "input", "overwrite": "true"},
            timeout=120,
        )
    response.raise_for_status()
    payload = response.json()
    name = str(payload.get("name") or path.name)
    subfolder = str(payload.get("subfolder") or "").strip("/")
    return f"{subfolder}/{name}" if subfolder else name


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


def _available_models(object_info: dict[str, Any], node: str, input_name: str) -> list[str]:
    try:
        value = object_info[node]["input"]["required"][input_name]
        if isinstance(value, list) and value and isinstance(value[0], list):
            return [str(item) for item in value[0]]
    except Exception:
        pass
    return []


def _anima_t2i_workflow(
    config: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
) -> dict[str, Any]:
    return {
        "44": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": config.get("unet_name", "anima_baseV10.safetensors"),
                "weight_dtype": "default",
            },
        },
        "45": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": config.get("clip_name", "qwen_3_06b_base.safetensors"),
                "type": "stable_diffusion",
                "device": "default",
            },
        },
        "15": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": config.get("vae_name", "qwen_image_vae.safetensors")},
        },
        "28": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "11": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["45", 0]},
        },
        "12": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["45", 0],
            },
        },
        "19": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["44", 0],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["28", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": config.get("sampler_name", "er_sde"),
                "scheduler": config.get("scheduler", "simple"),
                "denoise": 1,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["19", 0], "vae": ["15", 0]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": "AstrBot_ComfyUI/comfyui"},
        },
    }


def _anima_img2img_workflow(
    config: dict[str, Any],
    prompt: str,
    image_name: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
    denoise: float,
) -> dict[str, Any]:
    negative_prompt = str(config.get("negative_prompt", DEFAULT_CONFIG["negative_prompt"]))
    workflow = _anima_t2i_workflow(config, prompt, negative_prompt, width, height, steps, cfg, seed)
    workflow["10"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    workflow["13"] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": ["10", 0],
            "upscale_method": "lanczos",
            "width": width,
            "height": height,
            "crop": "disabled",
        },
    }
    workflow["14"] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": ["13", 0], "vae": ["15", 0]},
    }
    workflow["19"]["inputs"]["latent_image"] = ["14", 0]
    workflow["19"]["inputs"]["denoise"] = denoise
    workflow["9"]["inputs"]["filename_prefix"] = "AstrBot_ComfyUI/edit"
    return workflow


def _upscale_workflow(config: dict[str, Any], image_name: str, scale: float) -> dict[str, Any]:
    return {
        "10": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "20": {
            "class_type": "ImageScaleBy",
            "inputs": {"image": ["10", 0], "upscale_method": "lanczos", "scale_by": scale},
        },
        "30": {
            "class_type": "SaveImage",
            "inputs": {"images": ["20", 0], "filename_prefix": "AstrBot_ComfyUI/upscale"},
        },
    }


def _remove_bg_workflow(config: dict[str, Any], image_name: str) -> dict[str, Any]:
    return {
        "10": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "20": {
            "class_type": "BiRefNetRMBG",
            "inputs": {
                "image": ["10", 0],
                "model": config.get("remove_bg_model", "BiRefNet_lite"),
                "mask_blur": 1,
                "mask_offset": 0,
                "invert_output": False,
                "refine_foreground": True,
                "background": "Alpha",
                "background_color": "#222222",
            },
        },
        "30": {
            "class_type": "SaveImage",
            "inputs": {"images": ["20", 0], "filename_prefix": "AstrBot_ComfyUI/remove_bg"},
        },
    }


def _workflow(
    config: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
) -> dict[str, Any]:
    workflow = str(config.get("workflow") or "anima_t2i")
    if workflow != "anima_t2i":
        raise SystemExit(f"unsupported workflow: {workflow}")
    return _anima_t2i_workflow(config, prompt, negative_prompt, width, height, steps, cfg, seed)


def _history(config: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    data = _get_json(config, f"/history/{prompt_id}", timeout=20)
    item = data.get(prompt_id)
    return item if isinstance(item, dict) else None


def _download_image(config: dict[str, Any], image: dict[str, Any], index: int) -> Path:
    IMAGE_OUTPUTS.mkdir(parents=True, exist_ok=True)
    query = urlencode(
        {
            "filename": image.get("filename", ""),
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
    )
    response = requests.get(_base_url(config) + f"/view?{query}", timeout=120)
    response.raise_for_status()
    filename = str(image.get("filename") or f"comfyui_{index}.png")
    ext = Path(filename).suffix or ".png"
    output = IMAGE_OUTPUTS / f"{_now()}_comfyui_{index}{ext}"
    output.write_bytes(response.content)
    return output


def _output_images(history: dict[str, Any]) -> list[dict[str, Any]]:
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


def _run_prompt(config: dict[str, Any], prompt_body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    client_id = str(uuid.uuid4())
    submit = _post_json(config, "/prompt", {"prompt": prompt_body, "client_id": client_id}, timeout=20)
    prompt_id = str(submit.get("prompt_id") or "")
    if not prompt_id:
        raise RuntimeError(f"missing prompt_id: {submit}")
    timeout = max(1, int(config.get("timeout", 900)))
    poll_interval = max(1, int(config.get("poll_interval", 2)))
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = _history(config, prompt_id)
        if history:
            return prompt_id, history
        time.sleep(poll_interval)
    raise TimeoutError(f"timeout_after_{timeout}s")


def _save_history_images(config: dict[str, Any], history: dict[str, Any]) -> tuple[list[Path], int]:
    images = _output_images(history)
    outputs = [_download_image(config, image, idx) for idx, image in enumerate(images, start=1)]
    return outputs, len(images)


def _history_failed(history: dict[str, Any]) -> dict[str, Any] | None:
    status_payload = history.get("status") or {}
    if isinstance(status_payload, dict) and status_payload.get("status_str") not in {None, "success"}:
        return status_payload
    return None


def result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def status(args) -> None:
    config = load_config()
    payload: dict[str, Any] = {
        "ok": True,
        "enabled": bool(config.get("enabled", True)),
        "base_url": config.get("comfyui_base_url"),
        "workflow": config.get("workflow"),
        "allowed_sizes": [f"{width}x{height}" for width, height in _allowed_sizes(config)],
    }
    try:
        stats = _get_json(config, "/system_stats", timeout=10)
        object_info = _get_json(config, "/object_info", timeout=20)
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
    result(payload)


def recent(args) -> None:
    images = _recent_images(args.limit)
    payload = {"ok": True, "count": len(images), "images": []}
    for path in images:
        item = {
            "path": str(path),
            "relative_path": str(path.relative_to(WORKSPACE)),
            "size": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        }
        try:
            with Image.open(path) as img:
                item["width"] = img.width
                item["height"] = img.height
                item["format"] = img.format
        except Exception:
            pass
        payload["images"].append(item)
    result(payload)


def generate(args) -> None:
    config = load_config()
    if not config.get("enabled", True):
        result({"ok": False, "error": "comfyui agent is disabled"})
        return
    prompt = str(args.prompt or "").strip()
    if not prompt:
        result({"ok": False, "error": "missing prompt"})
        return
    try:
        width = int(args.width or config.get("width", DEFAULT_CONFIG["width"]))
        height = int(args.height or config.get("height", DEFAULT_CONFIG["height"]))
        width, height = _generation_size(config, width, height)
        steps = int(args.steps or config.get("steps", DEFAULT_CONFIG["steps"]))
        cfg = float(args.cfg or config.get("cfg", DEFAULT_CONFIG["cfg"]))
        seed = int(args.seed if args.seed is not None else random.randint(1, 2**32 - 1))
        negative_prompt = str(args.negative_prompt or config.get("negative_prompt", DEFAULT_CONFIG["negative_prompt"]))
        prompt_body = _workflow(config, prompt, negative_prompt, width, height, steps, cfg, seed)
        prompt_id, history = _run_prompt(config, prompt_body)
        status_payload = _history_failed(history)
        if status_payload:
            result({"ok": False, "error": "workflow_failed", "prompt_id": prompt_id, "status": status_payload})
            return
        outputs, raw_image_count = _save_history_images(config, history)
        result(
            {
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
        )
    except ValueError as exc:
        result({"ok": False, "error": str(exc)})
    except TimeoutError as exc:
        result({"ok": False, "error": str(exc)})
    except requests.HTTPError as exc:
        response = exc.response
        body = response.text[:2000] if response is not None else str(exc)
        result(
            {
                "ok": False,
                "error": "http_error",
                "status_code": response.status_code if response is not None else None,
                "body": body,
            }
        )
    except Exception as exc:
        result({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def edit(args) -> None:
    config = load_config()
    if not config.get("enabled", True):
        result({"ok": False, "error": "comfyui agent is disabled"})
        return
    prompt = str(args.prompt or "").strip()
    if not prompt:
        result({"ok": False, "error": "missing prompt"})
        return
    try:
        image = resolve_image(args.input)
        width, height = _image_size(image, int(config.get("max_image_side", 1024)))
        image_name = _upload_image(config, image)
        steps = int(args.steps or config.get("steps", 20))
        cfg = float(args.cfg or config.get("cfg", 4.0))
        denoise = float(args.denoise or config.get("edit_denoise", 0.55))
        seed = int(args.seed if args.seed is not None else random.randint(1, 2**32 - 1))
        prompt_body = _anima_img2img_workflow(config, prompt, image_name, width, height, steps, cfg, seed, denoise)
        prompt_id, history = _run_prompt(config, prompt_body)
        status_payload = _history_failed(history)
        if status_payload:
            result({"ok": False, "error": "workflow_failed", "prompt_id": prompt_id, "status": status_payload})
            return
        outputs, raw_image_count = _save_history_images(config, history)
        result(
            {
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
        )
    except ValueError as exc:
        result({"ok": False, "error": str(exc)})
    except TimeoutError as exc:
        result({"ok": False, "error": str(exc)})
    except requests.HTTPError as exc:
        response = exc.response
        body = response.text[:2000] if response is not None else str(exc)
        result({"ok": False, "error": "http_error", "status_code": response.status_code if response is not None else None, "body": body})
    except Exception as exc:
        result({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def upscale(args) -> None:
    config = load_config()
    if not config.get("enabled", True):
        result({"ok": False, "error": "comfyui agent is disabled"})
        return
    try:
        image = resolve_image(args.input)
        image_name = _upload_image(config, image)
        scale = float(args.scale or config.get("upscale_factor", 2.0))
        prompt_body = _upscale_workflow(config, image_name, scale)
        prompt_id, history = _run_prompt(config, prompt_body)
        status_payload = _history_failed(history)
        if status_payload:
            result({"ok": False, "error": "workflow_failed", "prompt_id": prompt_id, "status": status_payload})
            return
        outputs, raw_image_count = _save_history_images(config, history)
        result(
            {
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
        )
    except ValueError as exc:
        result({"ok": False, "error": str(exc)})
    except TimeoutError as exc:
        result({"ok": False, "error": str(exc)})
    except requests.HTTPError as exc:
        response = exc.response
        body = response.text[:2000] if response is not None else str(exc)
        result({"ok": False, "error": "http_error", "status_code": response.status_code if response is not None else None, "body": body})
    except Exception as exc:
        result({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def remove_bg(args) -> None:
    config = load_config()
    if not config.get("enabled", True):
        result({"ok": False, "error": "comfyui agent is disabled"})
        return
    try:
        image = resolve_image(args.input)
        image_name = _upload_image(config, image)
        prompt_body = _remove_bg_workflow(config, image_name)
        prompt_id, history = _run_prompt(config, prompt_body)
        status_payload = _history_failed(history)
        if status_payload:
            result({"ok": False, "error": "workflow_failed", "prompt_id": prompt_id, "status": status_payload})
            return
        outputs, raw_image_count = _save_history_images(config, history)
        result(
            {
                "ok": bool(outputs),
                "operation": "comfyui_remove_bg",
                "prompt_id": prompt_id,
                "input": str(image),
                "uploaded_image": image_name,
                "outputs": [str(path) for path in outputs],
                "raw_image_count": raw_image_count,
                "error": None if outputs else "no image found in history",
            }
        )
    except ValueError as exc:
        result({"ok": False, "error": str(exc)})
    except TimeoutError as exc:
        result({"ok": False, "error": str(exc)})
    except requests.HTTPError as exc:
        response = exc.response
        body = response.text[:2000] if response is not None else str(exc)
        result({"ok": False, "error": "http_error", "status_code": response.status_code if response is not None else None, "body": body})
    except Exception as exc:
        result({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="AstrBot ComfyUI agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status")
    p.set_defaults(func=status)

    p = sub.add_parser("recent")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=recent)

    p = sub.add_parser("generate")
    p.add_argument("--prompt", required=True)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--steps", type=int)
    p.add_argument("--cfg", type=float)
    p.add_argument("--seed", type=int)
    p.add_argument("--negative-prompt")
    p.set_defaults(func=generate)

    p = sub.add_parser("edit")
    p.add_argument("--prompt", required=True)
    p.add_argument("--input", default="latest")
    p.add_argument("--steps", type=int)
    p.add_argument("--cfg", type=float)
    p.add_argument("--denoise", type=float)
    p.add_argument("--seed", type=int)
    p.set_defaults(func=edit)

    p = sub.add_parser("upscale")
    p.add_argument("--input", default="latest")
    p.add_argument("--scale", type=float)
    p.set_defaults(func=upscale)

    p = sub.add_parser("remove-bg")
    p.add_argument("--input", default="latest")
    p.set_defaults(func=remove_bg)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
