from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from multi_person_prompt import (  # noqa: E402
    build_multi_person_plan_prompt,
    parse_multi_person_plan,
)
from prompt_background import (  # noqa: E402
    DEFAULT_PORTRAIT,
    EXPLICIT_SCENE,
    apply_default_portrait_tags,
    extract_background_mode,
)
from prompt_builder import build_final_prompt  # noqa: E402
from prompt_templates import build_llm_prompt  # noqa: E402


def test_background_marker_is_removed_before_tag_processing() -> None:
    tags, mode = extract_background_mode(
        "1girl, white dress, simple background, background_mode_default_portrait"
    )

    assert mode == DEFAULT_PORTRAIT
    assert tags == "1girl, white dress, simple background"

    tags, mode = extract_background_mode(
        "1girl, beach, sunset, background_mode_explicit_scene"
    )

    assert mode == EXPLICIT_SCENE
    assert "background_mode" not in tags


def test_default_portrait_adds_white_background_without_overriding_closeup() -> None:
    assert apply_default_portrait_tags("1girl, white dress") == (
        "1girl, white dress, full body, centered, simple background, white background"
    )
    closeup = apply_default_portrait_tags("1girl, close-up, smile")
    assert "full body" not in closeup
    assert "simple background" in closeup
    assert "white background" in closeup


def test_final_prompt_enforces_default_portrait_but_preserves_explicit_scene() -> None:
    config = {
        "chiyo_preset_enabled": False,
        "quality_prefix": "",
        "default_artist_tags": "",
        "style_tags": "",
    }
    default_result = build_final_prompt(
        user_prompt="白裙女孩",
        llm_content="1girl, white dress",
        config=config,
        background_mode=DEFAULT_PORTRAIT,
    )
    explicit_result = build_final_prompt(
        user_prompt="海边的白裙女孩",
        llm_content="1girl, white dress, beach, sunset",
        config=config,
        background_mode=EXPLICIT_SCENE,
    )

    assert "simple background" in default_result.content_tags
    assert "white background" in default_result.content_tags
    assert "full body" in default_result.content_tags
    assert "white background" not in explicit_result.content_tags
    assert "beach" in explicit_result.content_tags


def test_custom_template_still_receives_mandatory_llm_background_protocol() -> None:
    prompt = build_llm_prompt(
        "参考图视觉反推 tags：bedroom\n画狐莉穿这套衣服",
        prompt_builder_template="自定义规则：{theme}",
        original_theme="画狐莉穿这套衣服",
    )

    assert "自定义规则" in prompt
    assert "background_mode_default_portrait" in prompt
    assert "background_mode_explicit_scene" in prompt
    assert "用户原始文字：\n画狐莉穿这套衣服" in prompt


def test_multi_person_plan_uses_llm_background_mode_and_original_text() -> None:
    prompt = build_multi_person_plan_prompt(
        "参考图视觉反推 tags：classroom\n狐莉和团子牵手",
        original_user_prompt="狐莉和团子牵手",
    )

    assert "Original user text for background intent:\n狐莉和团子牵手" in prompt
    assert "Expanded request for all other visual details" in prompt

    plan = parse_multi_person_plan(
        """{
          "count_tags": ["2girls"],
          "common_tags": ["full body"],
          "characters": [{"name": "A"}, {"name": "B"}],
          "interactions": ["Character A holds Character B's hand."],
          "spatial_mode": "shared_contact",
          "background_mode": "default_portrait",
          "composition": "One unified view."
        }"""
    )

    assert plan is not None
    assert plan.background_mode == DEFAULT_PORTRAIT
