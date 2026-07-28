from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from prompt_presets import DEFAULT_QUALITY_TAGS  # noqa: E402
from prompt_templates import (  # noqa: E402
    DEFAULT_LLM_PROMPT_TEMPLATE,
)


def test_normal_variant_is_the_public_default() -> None:
    schema = json.loads((PLUGIN_DIR / "_conf_schema.json").read_text(encoding="utf-8"))
    sections = json.loads(
        (PLUGIN_DIR / "_conf_sections.json").read_text(encoding="utf-8")
    )
    connection = schema["anima_master_comfyui_connection"]["items"]
    style = schema["anima_master_style"]["items"]
    listed_items = [
        item for section in sections["sections"] for item in section.get("items", [])
    ]
    schema_items = [
        item
        for section in schema.values()
        if isinstance(section, dict) and section.get("type") == "object"
        for item in section.get("items", {})
    ]

    assert connection["custom_workflow_enabled"]["default"] is False
    assert connection["custom_workflow_override_parameters"]["default"] is False
    assert "custom_workflow_override_parameters" not in style
    assert sorted(listed_items) == sorted(schema_items)
    assert len(listed_items) == len(set(listed_items))
    assert "chiyo_preset" in listed_items
    assert "chiyo_preset_enabled" not in listed_items
    assert connection["custom_workflow_path"]["default"] == ""
    assert schema["anima_master_basic"]["items"]["chiyo_preset"]["options"] == [
        "",
        "base",
        "aesthetic",
        "turbo",
    ]
    assert (
        schema["anima_master_default_prompt"]["items"]["quality_prefix"]["default"]
        == DEFAULT_QUALITY_TAGS
    )
    assert (
        schema["anima_master_prompting"]["items"]["prompt_builder_template"]["default"]
        == DEFAULT_LLM_PROMPT_TEMPLATE
    )
    assert (
        schema["anima_master_prompting"]["items"]["prompt_builder_max_content_tags"][
            "default"
        ]
        == 65
    )


def test_advanced_example_uses_the_builtin_template() -> None:
    example = (PLUGIN_DIR / "docs" / "advanced-config.example.jsonc").read_text(
        encoding="utf-8"
    )
    match = re.search(r'"prompt_builder_template"\s*:\s*("(?:\\.|[^"\\])*")', example)

    assert match is not None
    assert '"custom_workflow_enabled": false' in example
    assert json.loads(match.group(1)) == DEFAULT_LLM_PROMPT_TEMPLATE


def test_builtin_template_prioritizes_one_pass_visual_quality() -> None:
    assert "一幅完整、协调、具有视觉吸引力的画面" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "可以自由决定服装细节、姿态、构图、镜头、背景" in (
        DEFAULT_LLM_PROMPT_TEMPLATE
    )
    assert "以最终图像协调、精致、有表现力和好看为优先" in (
        DEFAULT_LLM_PROMPT_TEMPLATE
    )
    assert "不需要机械追求固定 Tag 数量" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "保持用户明确指定的角色、主体、人数" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "40-55" not in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "50-65" not in DEFAULT_LLM_PROMPT_TEMPLATE


def test_turbo_variant_archive_contains_expected_workflow() -> None:
    workflow_path = (
        PLUGIN_DIR / "variants" / "turbo" / "workflows" / "comfyui_00051_api.json"
    )
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    lora_nodes = [
        node for node in workflow.values() if node.get("class_type") == "LoraLoader"
    ]
    sampler_nodes = [
        node for node in workflow.values() if node.get("class_type") == "KSampler"
    ]

    assert lora_nodes[0]["inputs"]["lora_name"] == "anima-turbo-lora-v0.2.safetensors"
    assert sampler_nodes[0]["inputs"]["steps"] == 10
    assert sampler_nodes[0]["inputs"]["cfg"] == 1.0
    assert sampler_nodes[0]["inputs"]["sampler_name"] == "euler"
    assert sampler_nodes[0]["inputs"]["scheduler"] == "simple"
