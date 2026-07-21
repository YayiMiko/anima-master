from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from prompt_builder import build_final_prompt  # noqa: E402


def _config() -> dict:
    return {
        "chiyo_preset_enabled": False,
        "fixed_characters": [
            "测试角色=1girl, solo, white hair, blue eyes, fox girl, fox ears,"
        ],
        "quality_prefix": "masterpiece, best quality,",
        "default_artist_tags": "@configured artist,",
        "style_tags": "",
    }


def test_fixed_character_content_keeps_only_non_identity_details() -> None:
    result = build_final_prompt(
        user_prompt="测试角色挥手",
        llm_content=(
            "masterpiece, best quality, @llm artist, white hair, blue eyes, "
            "loli, fox girl, fox ears, cute, kawaii, white dress, lace trim, "
            "waving, 2girls, crowd"
        ),
        config=_config(),
    )

    assert result.content_tags == "cute, kawaii, white dress, lace trim, waving"
    assert "@configured artist" in result.final_prompt
    assert "@llm artist" not in result.final_prompt


def test_explicit_multi_character_request_keeps_multi_character_tags() -> None:
    result = build_final_prompt(
        user_prompt="测试角色和另一人，双人构图",
        llm_content="2girls, multiple girls, holding hands, white dress",
        config=_config(),
    )

    assert "2girls" in result.content_tags
    assert "multiple girls" in result.content_tags
    assert "holding hands" in result.content_tags


def test_content_cleaning_has_no_tag_count_limit() -> None:
    tags = ", ".join(f"visual detail {index}" for index in range(150))

    result = build_final_prompt(
        user_prompt="无上限测试",
        llm_content=tags,
        config=_config(),
    )

    assert len(result.content_tags.split(", ")) == 150
