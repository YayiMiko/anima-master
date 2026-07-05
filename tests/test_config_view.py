from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from config_view import CONFIG_FIELD_GROUPS, build_config_debug_lines


def test_config_debug_lines_show_core_user_state(tmp_path: Path):
    config = {
        "chiyo_preset_enabled": True,
        "artist_presets": {"千代风格": "@a, @b"},
        "active_artist_preset": "千代风格",
        "fixed_characters": {"狐莉": "fox girl, green eyes"},
        "comfyui_base_url": "http://127.0.0.1:8188",
        "workflow": "my_workflow",
        "width": 1024,
        "height": 1536,
        "unet_name": "model.safetensors",
        "clip_name": "clip.safetensors",
        "vae_name": "vae.safetensors",
        "enable_verify": True,
        "verify_pass_score": 8,
        "max_verify_retry": 2,
    }

    lines = build_config_debug_lines(
        config,
        task_path=tmp_path / "last_task.json",
        task_exists=False,
    )
    text = "\n".join(lines)

    assert "千代预设：True" in text
    assert "当前画师组：千代风格" in text
    assert "角色：" in text and "狐莉" in text
    assert "ComfyUI：http://127.0.0.1:8188" in text
    assert "工作流：my_workflow" in text
    assert "默认尺寸：1024x1536" in text
    assert "生成后自检：True / 分数线 8 / 最多重画 2 次" in text
    assert "上次任务：暂无" in text


def test_config_field_groups_cover_debug_and_comfyui_sections():
    assert "comfyui_base_url" in CONFIG_FIELD_GROUPS["comfyui"]
    assert "workflow" in CONFIG_FIELD_GROUPS["comfyui"]
    assert "enable_verify" in CONFIG_FIELD_GROUPS["verify_debug"]
    assert "debug_prompt_enabled" in CONFIG_FIELD_GROUPS["verify_debug"]
