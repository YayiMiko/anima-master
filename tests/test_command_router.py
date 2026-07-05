from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from command_router import help_text, parse_hard_route


def test_parse_empty_anm_as_help():
    assert parse_hard_route("/anm") == ("help", "")


def test_parse_status_and_debug_status():
    assert parse_hard_route("/anm 状态") == ("status", "")
    assert parse_hard_route("/anm 调试状态") == ("debug_status", "")


def test_parse_generate_and_raw_generate():
    assert parse_hard_route("/anm 生图 一个女孩") == ("generate", "一个女孩")
    assert parse_hard_route("/anm 无优化 masterpiece, 1girl") == (
        "generate",
        "无优化 masterpiece, 1girl",
    )


def test_parse_spell_and_reverse():
    assert parse_hard_route("/anm 解析法术") == ("spell", "")
    assert parse_hard_route("/anm 反推") == ("reverse", "")


def test_parse_artist_and_character_commands():
    assert parse_hard_route("/anm 创建画师组 千代=@a, @b") == (
        "create_artist_preset",
        "千代=@a, @b",
    )
    assert parse_hard_route("/anm 切换画师组 千代") == ("use_artist_preset", "千代")
    assert parse_hard_route("/anm 添加角色 狐莉=1girl") == (
        "add_fixed_character",
        "狐莉=1girl",
    )


def test_help_text_uses_catalog_visibility():
    text = help_text(img2img_enabled=False)

    assert "/anm 生图 <描述>" in text
    assert "/anm 无优化 <tags>" in text
    assert "/anm 创建画师组" in text
    assert "/anm 切换画师组" in text
    assert "/anm 添加角色" in text
    assert "/anm 改图" not in text
