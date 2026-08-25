from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .prompt_presets import (
        active_artist_preset_name,
        active_artist_tags,
        active_style_tags,
        apply_config_preset,
        artist_presets,
        chiyo_profile_display_name,
        fixed_character_tags,
        style_presets,
    )
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from prompt_presets import (
        active_artist_preset_name,
        active_artist_tags,
        active_style_tags,
        apply_config_preset,
        artist_presets,
        chiyo_profile_display_name,
        fixed_character_tags,
        style_presets,
    )


CONFIG_FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "basic": (
        "prompt_optimize_enabled",
        "chiyo_preset",
        "admin_only",
        "allowed_sender_ids",
    ),
    "prompt": (
        "prompt_builder_template",
        "prompt_builder_provider_id",
        "prompt_builder_web_search_enabled",
        "prompt_builder_deep_thinking_enabled",
        "prompt_builder_reasoning_effort",
        "danbooru_core_tag_lookup_enabled",
    ),
    "character_style": (
        "fixed_characters",
        "artist_presets",
        "active_artist_preset",
        "default_artist_tags",
    ),
    "comfyui": (
        "comfyui_base_url",
        "workflow",
        "width",
        "height",
        "steps",
        "cfg",
        "sampler_name",
        "scheduler",
        "unet_name",
        "clip_name",
        "vae_name",
    ),
    "output": (
        "send_result_to_chat",
        "max_send_images",
        "img2img_enabled",
    ),
    "verify_debug": (
        "enable_verify",
        "verify_provider_id",
        "verify_pass_score",
        "max_verify_retry",
        "debug_prompt_enabled",
        "debug_image_reference_enabled",
        "debug_send_payload_enabled",
    ),
    "multi_person": (
        "multi_candidate_count",
        "multi_verify_enabled",
        "multi_verify_provider_id",
        "multi_verify_pass_score",
        "multi_send_degraded_candidate",
        "multi_show_degraded_notice",
        "multi_max_concurrent_generations",
    ),
}


def _bool(config: dict[str, Any], key: str, default: bool) -> bool:
    return bool(config.get(key, default))


def _int(config: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(config.get(key, default))
    except (TypeError, ValueError):
        return default


def _str(config: dict[str, Any], key: str, default: str = "") -> str:
    value = config.get(key, default)
    return str(value if value is not None else default)


def build_config_debug_lines(
    config: dict[str, Any],
    *,
    task_path: Path,
    task_exists: bool,
) -> list[str]:
    """Build the config section for `/anm 调试状态`.

    Args:
        config: Current plugin configuration.
        task_path: Path of `last_task.json`.
        task_exists: Whether `last_task.json` exists.

    Returns:
        User-facing, non-secret config summary lines.
    """
    config = apply_config_preset(dict(config or {}))
    prompt_config = config
    characters = sorted(fixed_character_tags(prompt_config).keys())
    presets = sorted(artist_presets(prompt_config).keys())
    active_artist = active_artist_preset_name(prompt_config)
    prompt_template = _str(config, "prompt_builder_template", "").strip()
    artist_tags = active_artist_tags(prompt_config).strip()
    style_tags = active_style_tags(prompt_config).strip()
    style_names = sorted(style_presets(prompt_config).keys())
    active_style = str(prompt_config.get("active_style_preset") or "").strip()
    lines = [
        "Anima 调试状态：",
        f"- 提示词优化：{_bool(config, 'prompt_optimize_enabled', True)}",
        f"- 自定义 Prompt 模板：{bool(prompt_template)}",
        f"- 千代预设：{chiyo_profile_display_name(prompt_config)}",
        f"- 低 CFG 提示词约束：{_bool(config, 'low_cfg_harness_enabled', False)}",
        f"- 画师 tags：{'已配置' if artist_tags else '未配置'}",
        f"- 当前画师预设：{active_artist or '默认画师 tags'}",
        f"- 已保存的画师预设：{', '.join(presets) if presets else '无'}",
        f"- 角色：{', '.join(characters) if characters else '无'}",
        f"- 联网搜索：{_bool(config, 'prompt_builder_web_search_enabled', True)}",
        f"- 深度思考：{_bool(config, 'prompt_builder_deep_thinking_enabled', True)} / {_str(config, 'prompt_builder_reasoning_effort', 'high')}",
        f"- Danbooru 核心 tag 查询：{_bool(config, 'danbooru_core_tag_lookup_enabled', True)}",
        f"- 图生图：{_bool(config, 'img2img_enabled', False)}",
        f"- 发送到聊天：{_bool(config, 'send_result_to_chat', True)} / 最多 {_int(config, 'max_send_images', 1)} 张",
        f"- 生成后自检：{_bool(config, 'enable_verify', False)} / 分数线 {_int(config, 'verify_pass_score', 7)} / 最多重画 {_int(config, 'max_verify_retry', 1)} 次",
        f"- 多人候选：{_int(config, 'multi_candidate_count', 2)} 张 / 自检 {_bool(config, 'multi_verify_enabled', True)} / 分数线 {_int(config, 'multi_verify_pass_score', 6)} / 降级发送 {_bool(config, 'multi_send_degraded_candidate', True)} / 并发 {_int(config, 'multi_max_concurrent_generations', 1)}",
        f"- ComfyUI：{_str(config, 'comfyui_base_url', 'http://127.0.0.1:8188')}",
        f"- 工作流：{_str(config, 'custom_workflow_path') if _bool(config, 'custom_workflow_enabled', False) else _str(config, 'workflow', 'anima_t2i')}",
        f"- 默认尺寸：{_int(config, 'width', 1024)}x{_int(config, 'height', 1536)}",
        f"- 模型：UNET={_str(config, 'unet_name', '') or '未配置'}，CLIP={_str(config, 'clip_name', '') or '未配置'}，VAE={_str(config, 'vae_name', '') or '未配置'}",
        f"- 调试开关：prompt={_bool(config, 'debug_prompt_enabled', False)}，reference={_bool(config, 'debug_image_reference_enabled', False)}，send={_bool(config, 'debug_send_payload_enabled', False)}",
        f"- 上次任务：{task_path if task_exists else '暂无'}",
    ]
    lines.extend(
        [
            f"- 当前画风：{active_style or ('已配置' if style_tags else '未配置')}",
            f"- 已保存画风：{', '.join(style_names) if style_names else '无'}",
        ]
    )
    return lines
