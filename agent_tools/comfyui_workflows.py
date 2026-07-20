from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULT_NEGATIVE_PROMPT = (
    "worst quality, low quality, score_1, score_2, score_3, artist name"
)


def anima_t2i_workflow(
    config: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
) -> dict[str, Any]:
    """Build the Anima text-to-image workflow graph."""
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
            "inputs": {
                "vae_name": config.get("vae_name", "qwen_image_vae.safetensors")
            },
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
                "scheduler": config.get("scheduler", "normal"),
                "denoise": 1,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["19", 0], "vae": ["15", 0]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": "astrbot/anm"},
        },
    }


def anima_img2img_workflow(
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
    """Build the Anima image-to-image workflow graph."""
    negative_prompt = str(config.get("negative_prompt", DEFAULT_NEGATIVE_PROMPT))
    workflow = anima_t2i_workflow(
        config, prompt, negative_prompt, width, height, steps, cfg, seed
    )
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
    workflow["9"]["inputs"]["filename_prefix"] = "astrbot/edit"
    return workflow


def upscale_workflow(
    config: dict[str, Any], image_name: str, scale: float
) -> dict[str, Any]:
    """Build a simple image upscale workflow graph."""
    return {
        "10": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "20": {
            "class_type": "ImageScaleBy",
            "inputs": {
                "image": ["10", 0],
                "upscale_method": "lanczos",
                "scale_by": scale,
            },
        },
        "30": {
            "class_type": "SaveImage",
            "inputs": {"images": ["20", 0], "filename_prefix": "astrbot/upscale"},
        },
    }


def remove_bg_workflow(config: dict[str, Any], image_name: str) -> dict[str, Any]:
    """Build a background-removal workflow graph."""
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
            "inputs": {"images": ["20", 0], "filename_prefix": "astrbot/remove_bg"},
        },
    }


def workflow(
    config: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
) -> dict[str, Any]:
    """Build the configured generation workflow graph."""
    if bool(config.get("custom_workflow_enabled", False)):
        return custom_t2i_workflow(
            config, prompt, negative_prompt, width, height, steps, cfg, seed
        )

    workflow_name = str(config.get("workflow") or "anima_t2i")
    if workflow_name != "anima_t2i":
        raise SystemExit(f"unsupported workflow: {workflow_name}")
    return anima_t2i_workflow(
        config, prompt, negative_prompt, width, height, steps, cfg, seed
    )


def custom_t2i_workflow(
    config: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
) -> dict[str, Any]:
    """Build a text-to-image workflow from a user-provided ComfyUI API JSON."""
    path_text = str(config.get("custom_workflow_path") or "").strip()
    if not path_text:
        raise SystemExit("custom_workflow_path_not_configured")

    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    if not path.exists():
        raise SystemExit(f"custom_workflow_not_found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    body = (
        raw.get("prompt")
        if isinstance(raw, dict) and isinstance(raw.get("prompt"), dict)
        else raw
    )
    if not isinstance(body, dict):
        raise SystemExit("custom_workflow_invalid_json")

    workflow_body = copy.deepcopy(body)
    _apply_custom_workflow_inputs(
        workflow_body, config, prompt, negative_prompt, width, height, steps, cfg, seed
    )
    return workflow_body


def _apply_custom_workflow_inputs(
    workflow_body: dict[str, Any],
    config: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
) -> None:
    text_nodes = _text_encode_nodes(workflow_body)
    positive_ids = _auto_positive_node_ids(text_nodes)
    negative_ids = _auto_negative_node_ids(text_nodes, positive_ids)

    if not positive_ids:
        raise SystemExit("custom_workflow_positive_node_not_found")

    for node_id in positive_ids:
        _set_node_input(workflow_body, node_id, "text", prompt)
    for node_id in negative_ids:
        _set_node_input(workflow_body, node_id, "text", negative_prompt)

    for node in workflow_body.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type == "SaveImage" and "filename_prefix" in inputs:
            inputs["filename_prefix"] = "astrbot/anm"
        if class_type == "EmptyLatentImage":
            if "width" in inputs:
                inputs["width"] = width
            if "height" in inputs:
                inputs["height"] = height
        if class_type in {"KSampler", "KSamplerAdvanced"}:
            for input_name, value in (
                ("steps", steps),
                ("cfg", cfg),
            ):
                if input_name in inputs:
                    inputs[input_name] = value
            for input_name in ("sampler_name", "scheduler"):
                configured = str(config.get(input_name) or "").strip()
                if configured and input_name in inputs:
                    inputs[input_name] = configured
        if "seed" in inputs:
            inputs["seed"] = seed
        if "noise_seed" in inputs:
            inputs["noise_seed"] = seed


def _text_encode_nodes(workflow_body: dict[str, Any]) -> list[str]:
    node_ids: list[str] = []
    for node_id, node in workflow_body.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if (
            "TextEncode" in class_type
            and isinstance(inputs, dict)
            and isinstance(inputs.get("text"), str)
        ):
            node_ids.append(str(node_id))
    return node_ids


def _auto_positive_node_ids(text_nodes: list[str]) -> list[str]:
    return text_nodes[:1]


def _auto_negative_node_ids(
    workflow_body_text_nodes: list[str], positive_ids: list[str]
) -> list[str]:
    return [
        node_id
        for node_id in workflow_body_text_nodes
        if node_id not in set(positive_ids)
    ][:1]


def _set_node_input(
    workflow_body: dict[str, Any], node_id: str, input_name: str, value: Any
) -> None:
    node = workflow_body.get(str(node_id))
    if not isinstance(node, dict):
        raise SystemExit(f"custom_workflow_node_not_found: {node_id}")
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise SystemExit(f"custom_workflow_node_has_no_inputs: {node_id}")
    inputs[input_name] = value
