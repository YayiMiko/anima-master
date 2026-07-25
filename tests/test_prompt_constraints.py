from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from prompt_builder import build_final_prompt  # noqa: E402
from prompt_constraints import parse_constraint_plan  # noqa: E402
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
