import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image


def _find_astrbot_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "main.py").exists() and (parent / "data").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = _find_astrbot_root()
WORKSPACE = ROOT / "workspace"
INPUTS = WORKSPACE / "inputs"
LATEST_INPUT = INPUTS / "latest.json"
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _inside_workspace(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(WORKSPACE.resolve())
    except ValueError:
        raise SystemExit(f"path is outside workspace: {path}")
    return resolved


def _json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


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


def _manifest_records() -> list[dict[str, Any]]:
    manifest = INPUTS / "manifest.jsonl"
    if not manifest.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("kind") == "image":
            records.append(item)
    return records


def _latest_image() -> Path:
    path = _path_from_record(_json_file(LATEST_INPUT))
    if path:
        return path
    candidates = []
    for record in reversed(_manifest_records()):
        path = _path_from_record(record)
        if path:
            candidates.append(path)
            break
    if candidates:
        return candidates[0]
    files = [p for p in INPUTS.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    if not files:
        raise SystemExit("no recent image found in workspace inputs")
    return max(files, key=lambda p: p.stat().st_mtime)


def _resolve_input(value: str | None, *, allow_outside: bool = False) -> Path:
    value = str(value or "latest").strip()
    if not value or value.lower() == "latest":
        return _latest_image()
    path = Path(value)
    if not path.is_absolute():
        path = WORKSPACE / path
    if not allow_outside:
        path = _inside_workspace(path)
    if not path.exists() or not path.is_file():
        raise SystemExit(f"input image not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise SystemExit(f"unsupported image type: {path.suffix}")
    return path.resolve()


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    return str(value)


def _json_loads_maybe(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _coerce_text(value).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _metadata(path: Path) -> dict[str, str]:
    with Image.open(path) as image:
        return {str(key): _coerce_text(value) for key, value in image.info.items()}


def _node_text(graph: dict[str, Any], node_id: str) -> str:
    node = graph.get(str(node_id))
    if not isinstance(node, dict):
        return ""
    inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
    text = inputs.get("text")
    if isinstance(text, str):
        return text.strip()
    return ""


def _node_ref(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return None


def _extract_comfyui_graph(graph: dict[str, Any]) -> dict[str, Any]:
    positive_ids: set[str] = set()
    negative_ids: set[str] = set()
    params: dict[str, Any] = {}
    models: dict[str, str] = {}
    width = height = None

    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if class_type in {"KSampler", "KSamplerAdvanced"}:
            positive = _node_ref(inputs.get("positive"))
            negative = _node_ref(inputs.get("negative"))
            if positive:
                positive_ids.add(positive)
            if negative:
                negative_ids.add(negative)
            for key in ("seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"):
                if key in inputs:
                    params[key] = inputs[key]
        elif class_type == "EmptyLatentImage":
            width = inputs.get("width", width)
            height = inputs.get("height", height)
        elif class_type == "UNETLoader" and inputs.get("unet_name"):
            models["unet"] = str(inputs.get("unet_name"))
        elif class_type == "CheckpointLoaderSimple" and inputs.get("ckpt_name"):
            models["checkpoint"] = str(inputs.get("ckpt_name"))
        elif class_type == "CLIPLoader" and inputs.get("clip_name"):
            models["clip"] = str(inputs.get("clip_name"))
        elif class_type == "VAELoader" and inputs.get("vae_name"):
            models["vae"] = str(inputs.get("vae_name"))

    positive = "\n".join(text for node_id in positive_ids if (text := _node_text(graph, node_id))).strip()
    negative = "\n".join(text for node_id in negative_ids if (text := _node_text(graph, node_id))).strip()
    if not positive:
        text_nodes = []
        for node_id, node in graph.items():
            if isinstance(node, dict) and "CLIPTextEncode" in str(node.get("class_type") or ""):
                text = _node_text(graph, str(node_id))
                if text:
                    text_nodes.append(text)
        if text_nodes:
            positive = text_nodes[0]
            if len(text_nodes) > 1 and not negative:
                negative = text_nodes[1]

    if width and height:
        params["size"] = f"{width}x{height}"
    if models:
        params["models"] = models
    return {
        "format": "comfyui_workflow",
        "positive_prompt": positive,
        "negative_prompt": negative,
        "parameters": params,
    }


def _split_webui_parameters(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        return {}
    negative = ""
    params_text = ""
    positive = raw
    neg_match = re.search(r"\nNegative prompt:\s*", raw, flags=re.I)
    if neg_match:
        positive = raw[: neg_match.start()].strip()
        rest = raw[neg_match.end() :]
        steps_match = re.search(r"\nSteps:\s*", rest, flags=re.I)
        if steps_match:
            negative = rest[: steps_match.start()].strip()
            params_text = "Steps: " + rest[steps_match.end() :].strip()
        else:
            negative = rest.strip()
    else:
        steps_match = re.search(r"\nSteps:\s*", raw, flags=re.I)
        if steps_match:
            positive = raw[: steps_match.start()].strip()
            params_text = "Steps: " + raw[steps_match.end() :].strip()

    params: dict[str, str] = {}
    for part in re.split(r",\s*", params_text):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            params[key] = value
    return {
        "format": "webui_parameters",
        "positive_prompt": positive,
        "negative_prompt": negative,
        "parameters": params,
        "full_generation_info": raw,
    }


def _extract_json_generation(data: dict[str, Any]) -> dict[str, Any]:
    positive = data.get("prompt") or data.get("positive_prompt") or data.get("positive")
    negative = data.get("uc") or data.get("negative_prompt") or data.get("negative")
    if not positive and not negative:
        return {}
    params = {}
    for key in ("steps", "scale", "cfg", "seed", "sampler", "sampler_name", "width", "height", "model"):
        if key in data:
            params[key] = data[key]
    if "width" in params and "height" in params:
        params["size"] = f"{params['width']}x{params['height']}"
    return {
        "format": "json_generation_info",
        "positive_prompt": _coerce_text(positive).strip(),
        "negative_prompt": _coerce_text(negative).strip(),
        "parameters": params,
        "full_generation_info": data,
    }


def _has_prompt_payload(payload: dict[str, Any]) -> bool:
    return bool(
        str(payload.get("metadata_format") or "").strip()
        or str(payload.get("positive_prompt") or "").strip()
        or str(payload.get("negative_prompt") or "").strip()
    )


def inspect_image(path: Path, *, include_raw: bool = False) -> dict[str, Any]:
    metadata = _metadata(path)
    payload: dict[str, Any] = {
        "ok": True,
        "input": str(path),
        "relative_path": str(path.relative_to(WORKSPACE)) if path.is_relative_to(WORKSPACE) else None,
        "size": path.stat().st_size,
        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "metadata_keys": sorted(metadata.keys()),
        "metadata_format": "",
        "positive_prompt": "",
        "negative_prompt": "",
        "parameters": {},
    }
    with Image.open(path) as image:
        payload.update({"width": image.width, "height": image.height, "format": image.format, "mode": image.mode})

    for key in ("prompt", "workflow"):
        graph = _json_loads_maybe(metadata.get(key))
        if isinstance(graph, dict) and any(isinstance(v, dict) and "class_type" in v for v in graph.values()):
            extracted = _extract_comfyui_graph(graph)
            payload.update(
                {
                    "metadata_format": extracted.get("format", ""),
                    "positive_prompt": extracted.get("positive_prompt", ""),
                    "negative_prompt": extracted.get("negative_prompt", ""),
                    "parameters": extracted.get("parameters", {}),
                }
            )
            if include_raw:
                payload["raw_metadata"] = metadata
            return payload

    for key in ("parameters", "Parameters"):
        if metadata.get(key):
            extracted = _split_webui_parameters(metadata[key])
            payload.update(
                {
                    "metadata_format": extracted.get("format", ""),
                    "positive_prompt": extracted.get("positive_prompt", ""),
                    "negative_prompt": extracted.get("negative_prompt", ""),
                    "parameters": extracted.get("parameters", {}),
                    "full_generation_info": extracted.get("full_generation_info", ""),
                }
            )
            if include_raw:
                payload["raw_metadata"] = metadata
            return payload

    for key in ("Comment", "comment", "Description", "generation_data"):
        data = _json_loads_maybe(metadata.get(key))
        if isinstance(data, dict):
            extracted = _extract_json_generation(data)
            if extracted:
                payload.update(
                    {
                        "metadata_format": extracted.get("format", ""),
                        "positive_prompt": extracted.get("positive_prompt", ""),
                        "negative_prompt": extracted.get("negative_prompt", ""),
                        "parameters": extracted.get("parameters", {}),
                        "full_generation_info": extracted.get("full_generation_info", {}),
                    }
                )
                if include_raw:
                    payload["raw_metadata"] = metadata
                return payload
        elif metadata.get(key):
            extracted = _split_webui_parameters(metadata[key])
            if extracted.get("positive_prompt"):
                payload.update(
                    {
                        "metadata_format": extracted.get("format", ""),
                        "positive_prompt": extracted.get("positive_prompt", ""),
                        "negative_prompt": extracted.get("negative_prompt", ""),
                        "parameters": extracted.get("parameters", {}),
                        "full_generation_info": extracted.get("full_generation_info", ""),
                    }
                )
                if include_raw:
                    payload["raw_metadata"] = metadata
                return payload

    if include_raw:
        payload["raw_metadata"] = metadata
    return payload


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_inspect(args) -> None:
    path = _resolve_input(args.input, allow_outside=args.allow_outside)
    _print(inspect_image(path, include_raw=args.include_raw))


def cmd_positive(args) -> None:
    path = _resolve_input(args.input, allow_outside=args.allow_outside)
    payload = inspect_image(path)
    _print(
        {
            "ok": True,
            "input": str(path),
            "metadata_format": payload.get("metadata_format", ""),
            "positive_prompt": payload.get("positive_prompt", ""),
        }
    )


def cmd_negative(args) -> None:
    path = _resolve_input(args.input, allow_outside=args.allow_outside)
    payload = inspect_image(path)
    _print(
        {
            "ok": True,
            "input": str(path),
            "metadata_format": payload.get("metadata_format", ""),
            "negative_prompt": payload.get("negative_prompt", ""),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract generation prompts from image metadata")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func in (("inspect", cmd_inspect), ("positive", cmd_positive), ("negative", cmd_negative)):
        p = sub.add_parser(name)
        p.add_argument("--input", default="latest")
        p.add_argument("--allow-outside", action="store_true")
        if name == "inspect":
            p.add_argument("--include-raw", action="store_true")
        p.set_defaults(func=func)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
