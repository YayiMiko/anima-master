from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from prompt_builder import build_final_prompt  # noqa: E402
from prompt_constraints import (  # noqa: E402
    apply_scene_gate,
    parse_constraint_plan,
    retry_preserves_prompt,
    scene_gate_open,
)
from tag_cleaner import split_tags  # noqa: E402


def test_low_cfg_constraint_plan_reorders_weights_removes_and_limits() -> None:
    plan = parse_constraint_plan(
        json.dumps(
            {
                "has_constraints": True,
                "style_tags": ["watercolor"],
                "priority_tags": ["holding sword"],
                "remove_tags": ["holding umbrella"],
                "max_content_tags": 20,
                "reason": "Protect the requested action.",
            }
        )
    )
    candidate = ", ".join(
        ["holding umbrella", "standing"] + [f"detail {index}" for index in range(30)]
    )

    result = build_final_prompt(
        user_prompt="水彩风格，手持长剑",
        llm_content=candidate,
        config={"chiyo_preset": "turbo"},
        constraint_plan=plan,
    )

    assert result.constraint_mode is True
    assert result.weighted_style_tags == ("(watercolor:2)",)
    assert split_tags(result.content_tags)[0] == "holding sword"
    assert "holding umbrella" not in result.content_tags
    assert len(split_tags(result.content_tags)) == 20
    assert result.constraint_reason == "Protect the requested action."


def test_invalid_constraint_plan_keeps_normal_prompt_behavior() -> None:
    result = build_final_prompt(
        user_prompt="蓝色连衣裙",
        llm_content="blue dress, standing",
        config={"chiyo_preset": "base"},
        constraint_plan=parse_constraint_plan("not json"),
    )

    assert result.constraint_mode is False
    assert result.content_tags == "blue dress, standing"
    assert not result.weighted_style_tags


def test_scene_gate_removes_unrequested_scene_tags() -> None:
    filtered, removed = apply_scene_gate(
        "1girl, blue dress, soft lighting, floating particles, smile",
        enabled=False,
    )

    assert filtered == "1girl, blue dress, smile"
    assert removed == ("soft lighting", "floating particles")
    assert scene_gate_open("蓝色连衣裙女孩微笑") is False
    assert scene_gate_open("蓝色连衣裙女孩站在夜景背景中") is True


def test_longer_retry_is_rejected_when_it_changes_core_content() -> None:
    original = "wakaba_mutsumi, white dress, holding violin, gentle smile"
    retry = ", ".join(
        ["different_character, black armor, holding sword"]
        + [f"extra detail {index}" for index in range(50)]
    )

    assert (
        retry_preserves_prompt(
            original_tags=original,
            retry_tags=retry,
            required_core_tags=("wakaba_mutsumi",),
            removed_scene_tags=(),
        )
        is False
    )
