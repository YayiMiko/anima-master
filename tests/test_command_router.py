from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from command_router import (  # noqa: E402
    help_text,
    parse_generation_size,
    parse_hard_route,
)

ALLOWED_SIZES = [
    (832, 1216),
    (896, 1152),
    (1024, 1024),
    (1152, 896),
    (1216, 832),
    (768, 1344),
    (1344, 768),
    (1024, 1536),
]


def test_parse_empty_anm_as_help():
    assert parse_hard_route("/anm") == ("help", "")


def test_parse_status_and_debug_status():
    assert parse_hard_route("/anm 状态") == ("status", "")
    assert parse_hard_route("/anm 调试状态") == ("debug_status", "")


def test_parse_generate_and_raw_generate():
    assert parse_hard_route("/anm 生图 一个女孩") == ("generate", "一个女孩")
    assert parse_hard_route("/anm 多人 左边一个女孩，右边一个男孩") == (
        "multi_person",
        "左边一个女孩，右边一个男孩",
    )
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
    assert "/anm 多人 <描述>" in text
    assert "/anm 无优化 <tags>" in text
    assert "/anm 创建画师组" in text
    assert "/anm 切换画师组" in text
    assert "/anm 添加角色" in text
    assert "--尺寸 1216x832" in text
    assert "--自由发挥" not in text
    assert "/anm 改图" not in text


def test_parse_generation_size_aliases_choose_closest_allowed_ratio():
    assert parse_generation_size("竖图：狐莉站在梨花树下", ALLOWED_SIZES) == (
        "狐莉站在梨花树下",
        (1024, 1536),
        None,
    )
    assert parse_generation_size("宽屏 远景山谷", ALLOWED_SIZES) == (
        "远景山谷",
        (1344, 768),
        None,
    )


def test_parse_generation_size_explicit_forms_remove_control_text():
    assert parse_generation_size("1024x1536：白色礼服少女", ALLOWED_SIZES) == (
        "白色礼服少女",
        (1024, 1536),
        None,
    )
    assert parse_generation_size("少女站在河岸 --尺寸 1216x832", ALLOWED_SIZES) == (
        "少女站在河岸",
        (1216, 832),
        None,
    )


def test_parse_generation_size_rejects_unavailable_explicit_size():
    prompt, size, error = parse_generation_size(
        "分辨率 1000x1400，白色礼服少女", ALLOWED_SIZES
    )

    assert prompt == "白色礼服少女"
    assert size is None
    assert error and "1000x1400 不可用" in error


def test_parse_generation_size_does_not_consume_alias_prefix():
    assert parse_generation_size("宽屏幕上的少女", ALLOWED_SIZES) == (
        "宽屏幕上的少女",
        None,
        None,
    )


def test_multi_person_keyword_requires_a_command_boundary():
    assert parse_hard_route("/anm \u591a\u4eba\u56f4\u89c2\u4e00\u53ea\u732b") == (
        "generate",
        "\u591a\u4eba\u56f4\u89c2\u4e00\u53ea\u732b",
    )
    assert parse_hard_route(
        "/anm \u591a\u4eba\uff1a\u5de6\u8fb9\u4e00\u4eba\uff0c\u53f3\u8fb9\u4e00\u4eba"
    ) == (
        "multi_person",
        "\u5de6\u8fb9\u4e00\u4eba\uff0c\u53f3\u8fb9\u4e00\u4eba",
    )
