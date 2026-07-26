from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from prompt_builder import build_final_prompt  # noqa: E402
from tag_cleaner import clean_content_tags  # noqa: E402


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


def test_content_cleaning_uses_default_content_tag_limit() -> None:
    tags = ", ".join(f"visual detail {index}" for index in range(150))

    result = build_final_prompt(
        user_prompt="上限测试",
        llm_content=tags,
        config=_config(),
    )

    assert len(result.content_tags.split(", ")) == 65
    assert len(result.final_prompt.split(", ")) == 68
    assert "@configured artist" in result.final_prompt


def test_content_tag_limit_can_be_configured() -> None:
    tags = ", ".join(f"visual detail {index}" for index in range(20))
    config = _config()
    config["prompt_builder_max_content_tags"] = 12

    result = build_final_prompt(
        user_prompt="自定义上限测试",
        llm_content=tags,
        config=config,
    )

    assert len(result.content_tags.split(", ")) == 12


def test_raw_mode_does_not_apply_content_tag_limit() -> None:
    tags = ", ".join(f"raw detail {index}" for index in range(120))

    result = build_final_prompt(
        user_prompt=f"raw {tags}",
        llm_content="ignored",
        config=_config(),
    )

    assert result.raw_mode is True
    assert len(result.content_tags.split(", ")) == 120


def test_content_cleaner_removes_high_confidence_semantic_conflicts() -> None:
    cleaned = clean_content_tags(
        "{{holding sword}}, Point a sword at the audience, looking away, "
        "looking at viewer, nude, naked, topless, bottomless, holding nothing, "
        "mist, morning mist, pear blossoms, punis, sheer fabric, "
        "translucent fabric",
        strip_character_tags=False,
    )

    assert "sword pointed at viewer" in cleaned
    assert "holding sword" in cleaned
    assert "looking away" in cleaned
    assert "looking at viewer" not in cleaned
    assert "nude" in cleaned
    assert "naked" not in cleaned
    assert "topless" not in cleaned
    assert "bottomless" not in cleaned
    assert "holding nothing" not in cleaned
    assert "morning mist" in cleaned
    assert ", mist," not in f", {cleaned},"
    assert "pear blossoms" in cleaned
    assert "penis" in cleaned
    assert "punis" not in cleaned
    assert "sheer fabric" in cleaned
    assert "translucent fabric" not in cleaned


def test_content_cleaner_removes_viewer_gaze_when_eyes_are_closed() -> None:
    cleaned = clean_content_tags(
        "looking up at viewer, singing, closed eyes, gentle smile",
        strip_character_tags=False,
    )

    assert "looking up at viewer" not in cleaned
    assert cleaned == "singing, closed eyes, gentle smile"


def test_fixed_character_cleaning_preserves_explicit_hair_details() -> None:
    cleaned = clean_content_tags(
        "white hair, blue eyes, fox girl, lotus hair ornament, floating hair, "
        "braid, pubic hair",
        strip_character_tags=True,
    )

    assert cleaned == "lotus hair ornament, floating hair, braid, pubic hair"


def test_content_cleaner_limits_synonyms_without_removing_distinct_light_roles() -> (
    None
):
    cleaned = clean_content_tags(
        "light rays, sunbeams, glowing, illuminated, bright, luminous, radiant, "
        "backlighting, rim lighting, cast shadows, floating particles, "
        "light particles, flowing dress, dress flowing, embroidered hem",
        strip_character_tags=False,
    )

    assert cleaned == (
        "light rays, glowing, illuminated, backlighting, rim lighting, "
        "cast shadows, floating particles, flowing dress, embroidered hem"
    )
