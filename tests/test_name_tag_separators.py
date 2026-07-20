from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from command_actions import CommandActionHandler  # noqa: E402
from prompt_builder import build_final_prompt  # noqa: E402
from prompt_presets import (  # noqa: E402
    active_style_tags,
    apply_config_preset,
    artist_presets,
    fixed_character_tags,
    style_presets,
)


def test_command_parser_accepts_fullwidth_equals() -> None:
    handler = CommandActionHandler.__new__(CommandActionHandler)

    assert handler._parse_name_tags("狐莉＝1girl, solo") == (
        "狐莉",
        "1girl, solo,",
    )


def test_character_config_accepts_fullwidth_separators() -> None:
    config = {"fixed_characters": ["狐莉＝1girl, solo", "团子：1girl, vampire"]}

    assert fixed_character_tags(config) == {
        "狐莉": "1girl, solo",
        "团子": "1girl, vampire",
    }


def test_artist_config_accepts_fullwidth_separators() -> None:
    config = {"artist_presets": ["平涂＝@artist_a, @artist_b", "柔光：@artist_c"]}

    assert artist_presets(config) == {
        "平涂": "@artist_a, @artist_b",
        "柔光": "@artist_c",
    }


def test_style_tags_follow_artist_tags() -> None:
    result = build_final_prompt(
        user_prompt="少女",
        llm_content="1girl, solo",
        config={
            "active_artist_preset": "画师",
            "artist_presets": ["画师=@artist_a,"],
            "style_tags": "anime coloring, cel shading,",
        },
    )

    assert result.final_prompt.index("anime coloring") < result.final_prompt.index(
        "1girl"
    )


def test_saved_style_preset_is_selected_over_fallback() -> None:
    config = {
        "style_tags": "fallback style",
        "style_presets": ["高精立绘＝anime coloring, cel shading"],
        "active_style_preset": "高精立绘",
    }

    assert style_presets(config) == {"高精立绘": "anime coloring, cel shading"}
    assert active_style_tags(config) == "anime coloring, cel shading"


def test_style_tags_work_without_artist_group() -> None:
    result = build_final_prompt(
        user_prompt="少女",
        llm_content="1girl, solo",
        config={"style_tags": "anime coloring, cel shading"},
    )

    assert result.used_default_style is True
    assert "anime coloring" in result.final_prompt


def test_star_knight_preset_adds_artist_and_style_variants() -> None:
    config = apply_config_preset({"star_knight_preset_enabled": True})

    assert config["active_artist_preset"] == "闪耀星骑士主组"
    assert config["active_style_preset"] == "闪耀星骑士基础"
    assert "闪耀星骑士科技魔女" in style_presets(config)
    assert "@kithera" in artist_presets(config)["闪耀星骑士主组"]
