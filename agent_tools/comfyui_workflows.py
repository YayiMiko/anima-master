from __future__ import annotations

from typing import Any


DEFAULT_NEGATIVE_PROMPT = "worst quality, low quality, artist name"


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
    workflow = anima_t2i_workflow(config, prompt, negative_prompt, width, height, steps, cfg, seed)
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


def upscale_workflow(config: dict[str, Any], image_name: str, scale: float) -> dict[str, Any]:
    """Build a simple image upscale workflow graph."""
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
            "inputs": {"images": ["20", 0], "filename_prefix": "AstrBot_ComfyUI/remove_bg"},
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
    workflow_name = str(config.get("workflow") or "anima_t2i")
    if workflow_name != "anima_t2i":
        raise SystemExit(f"unsupported workflow: {workflow_name}")
    return anima_t2i_workflow(config, prompt, negative_prompt, width, height, steps, cfg, seed)
