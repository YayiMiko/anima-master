from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from outfit_transfer import (
    build_outfit_transfer_context,
    detect_outfit_transfer,
    filter_outfit_tags,
)


def test_detects_named_outfit_transfer_to_fixed_character():
    plan = detect_outfit_transfer("联网检索碧蓝档案角色妃咲，深度思考后将其服饰应用于狐莉身上", "狐莉")

    assert plan.enabled is True
    assert plan.source_subject == "妃咲"
    assert plan.target_character == "狐莉"
    assert plan.source_from_search is True


def test_no_fixed_character_does_not_force_outfit_transfer():
    plan = detect_outfit_transfer("联网检索碧蓝档案角色妃咲的服装", "")

    assert plan.enabled is False


def test_filter_outfit_tags_drops_identity_features():
    filtered = filter_outfit_tags(
        "blue hair, red eyes, fox ears, tail, white dress, ribbon, gold trim, boots"
    )

    assert "white dress" in filtered
    assert "ribbon" in filtered
    assert "gold trim" in filtered
    assert "boots" in filtered
    assert "blue hair" not in filtered
    assert "red eyes" not in filtered
    assert "fox ears" not in filtered
    assert "tail" not in filtered


def test_outfit_transfer_context_filters_reference_tags():
    plan = detect_outfit_transfer("狐莉穿上图中角色的衣服\n参考图视觉反推 tags：blue hair, red eyes, white dress, ribbon, boots", "狐莉")
    context = build_outfit_transfer_context(plan, prompt=plan.directive_prompt + "\n参考图视觉反推 tags：blue hair, red eyes, white dress, ribbon, boots")

    assert context.enabled is True
    assert context.outfit_summary_source == "reference_filter"
    assert "white dress" in context.outfit_summary
    assert "ribbon" in context.outfit_summary
    assert "blue hair" not in context.outfit_summary
    assert "red eyes" not in context.outfit_summary
    assert "hair" in context.forbidden_identity_features
