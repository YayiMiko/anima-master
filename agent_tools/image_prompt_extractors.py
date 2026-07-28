from __future__ import annotations

import json
import re
from typing import Any

from image_metadata_reader import coerce_text


def json_loads_maybe(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = coerce_text(value).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def extract_comfyui_graph(graph: dict[str, Any]) -> dict[str, Any]:
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

    positive = "\n".join(
        text for node_id in positive_ids if (text := _node_text(graph, node_id))
    ).strip()
    negative = "\n".join(
        text for node_id in negative_ids if (text := _node_text(graph, node_id))
    ).strip()
    if not positive:
        text_nodes = []
        for node_id, node in graph.items():
            if isinstance(node, dict) and "CLIPTextEncode" in str(
                node.get("class_type") or ""
            ):
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


def split_webui_parameters(text: str) -> dict[str, Any]:
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


def extract_json_generation(data: dict[str, Any]) -> dict[str, Any]:
    positive = data.get("prompt") or data.get("positive_prompt") or data.get("positive")
    negative = data.get("uc") or data.get("negative_prompt") or data.get("negative")
    if not positive and not negative:
        return {}
    params = {}
    for key in (
        "steps",
        "scale",
        "cfg",
        "seed",
        "sampler",
        "sampler_name",
        "width",
        "height",
        "model",
    ):
        if key in data:
            params[key] = data[key]
    if "width" in params and "height" in params:
        params["size"] = f"{params['width']}x{params['height']}"
    return {
        "format": "json_generation_info",
        "positive_prompt": coerce_text(positive).strip(),
        "negative_prompt": coerce_text(negative).strip(),
        "parameters": params,
        "full_generation_info": data,
    }


def has_prompt_payload(payload: dict[str, Any]) -> bool:
    return bool(
        str(payload.get("metadata_format") or "").strip()
        or str(payload.get("positive_prompt") or "").strip()
        or str(payload.get("negative_prompt") or "").strip()
    )


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
