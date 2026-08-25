import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from comfyui_command_runner import run_cli_action
from comfyui_inputs import ComfyUIImageResolver
from comfyui_operations import (
    edit_payload,
    generate_payload,
    remove_bg_payload,
    upscale_payload,
)
from comfyui_sizes import allowed_sizes
from comfyui_status import build_status_payload
from PIL import Image

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from prompt_presets import apply_config_preset  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _find_astrbot_root() -> Path:
    candidates = (Path.cwd().resolve(), *Path(__file__).resolve().parents)
    for candidate in candidates:
        has_runtime = (candidate / "astrbot").is_dir() or (
            candidate / ".astrbot"
        ).exists()
        has_runtime = has_runtime or (candidate / "data" / "config").is_dir()
        if has_runtime and (candidate / "data").is_dir():
            return candidate
    return Path(__file__).resolve().parents[1]


ROOT = _find_astrbot_root()
WORKSPACE = ROOT / "workspace"
OUTPUTS = WORKSPACE / "outputs"
IMAGE_OUTPUTS = OUTPUTS / "images"
CONFIG = ROOT / "data" / "config" / "astrbot_plugin_anima_master_config.json"
IMAGE_RESOLVER = ComfyUIImageResolver(WORKSPACE)


DEFAULT_CONFIG = {
    "comfyui_base_url": "http://127.0.0.1:8188",
    "workflow": "anima_t2i",
    "custom_workflow_enabled": False,
    "custom_workflow_path": "",
    "timeout": 300,
    "poll_interval": 2,
    "width": 1024,
    "height": 1536,
    "allowed_sizes": [
        "832x1216",
        "896x1152",
        "1024x1024",
        "1152x896",
        "1216x832",
        "768x1344",
        "1344x768",
        "1024x1536",
    ],
    "steps": 30,
    "cfg": 5.0,
    "sampler_name": "er_sde",
    "scheduler": "normal",
    "unet_name": "anima_baseV10.safetensors",
    "clip_name": "qwen_3_06b_base.safetensors",
    "vae_name": "qwen_image_vae.safetensors",
    "negative_prompt": "worst quality, low quality, score_1, score_2, score_3, artist name",
    "edit_denoise": 0.55,
    "max_image_side": 1024,
    "upscale_factor": 2.0,
    "remove_bg_model": "BiRefNet_lite",
}


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
    config.update(_flatten_config(_json_file(CONFIG)))
    return apply_config_preset(config)


def _flatten_config(config: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in dict(config or {}).items():
        if str(key).startswith("anima_master_") and isinstance(value, dict):
            flat.update(value)
    for key, value in dict(config or {}).items():
        if not (str(key).startswith("anima_master_") and isinstance(value, dict)):
            flat[key] = value
    return flat


def _inside_workspace(path: Path) -> Path:
    return IMAGE_RESOLVER.inside_workspace(path)


def _manifest_records() -> list[dict[str, Any]]:
    return IMAGE_RESOLVER.manifest_records()


def _path_from_record(record: dict[str, Any]) -> Path | None:
    return IMAGE_RESOLVER.path_from_record(record)


def _recent_images(limit: int) -> list[Path]:
    return IMAGE_RESOLVER.recent_images(limit)


def _latest_image() -> Path:
    return IMAGE_RESOLVER.latest_image()


def resolve_image(value: str | None) -> Path:
    return IMAGE_RESOLVER.resolve_image(value)


def result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def status(args) -> None:
    config = load_config()
    size_options = [
        f"{width}x{height}"
        for width, height in allowed_sizes(config, DEFAULT_CONFIG["allowed_sizes"])
    ]
    result(
        build_status_payload(
            config,
            size_options,
            include_capabilities=not args.quick,
        )
    )


def recent(args) -> None:
    images = _recent_images(args.limit)
    payload = {"ok": True, "count": len(images), "images": []}
    for path in images:
        item = {
            "path": str(path),
            "relative_path": str(path.relative_to(WORKSPACE)),
            "size": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(
                timespec="seconds"
            ),
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
    prompt = str(args.prompt or "").strip()
    if not prompt:
        result({"ok": False, "error": "missing_prompt", "message": "缺少提示词"})
        return

    result(
        run_cli_action(
            lambda: generate_payload(
                config, DEFAULT_CONFIG, IMAGE_OUTPUTS, args, prompt
            )
        )
    )


def edit(args) -> None:
    config = load_config()
    prompt = str(args.prompt or "").strip()
    if not prompt:
        result({"ok": False, "error": "missing_prompt", "message": "缺少提示词"})
        return

    result(
        run_cli_action(
            lambda: edit_payload(config, IMAGE_OUTPUTS, resolve_image, args, prompt)
        )
    )


def upscale(args) -> None:
    config = load_config()

    result(
        run_cli_action(
            lambda: upscale_payload(config, IMAGE_OUTPUTS, resolve_image, args)
        )
    )


def remove_bg(args) -> None:
    config = load_config()

    result(
        run_cli_action(
            lambda: remove_bg_payload(config, IMAGE_OUTPUTS, resolve_image, args)
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AstrBot ComfyUI 助手")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status")
    p.add_argument(
        "--quick",
        action="store_true",
        help="只检查 ComfyUI API 存活，不读取模型和节点能力",
    )
    p.set_defaults(func=status)

    p = sub.add_parser("recent")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=recent)

    p = sub.add_parser("generate")
    p.add_argument("--prompt", required=True)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--override-size", action="store_true")
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
