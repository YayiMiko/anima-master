from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from anima.runtime.config_view import build_config_debug_lines  # noqa: E402


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

    assert "千代预设：千代base" in text
    assert "当前画师预设：已启用" in text
    assert "固定角色：1 个" in text and "狐莉" not in text
    assert "ComfyUI 地址：已配置" in text
    assert "127.0.0.1" not in text
    assert "工作流：内置" in text
    assert "my_workflow" not in text
    assert "默认尺寸：1024x1536" in text
    assert "生成后自检：True / 分数线 8 / 最多重画 2 次" in text
    assert "上次任务：暂无" in text


def test_config_debug_lines_show_effective_turbo_profile(tmp_path: Path):
    lines = build_config_debug_lines(
        {"chiyo_preset": "turbo"},
        task_path=tmp_path / "last_task.json",
        task_exists=False,
    )
    text = "\n".join(lines)

    assert "千代预设：千代turbo" in text
    assert "低 CFG 提示词约束：True" in text
    assert "工作流：自定义" in text
    assert "UNET=已配置" in text
