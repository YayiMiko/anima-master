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


def test_builtin_template_uses_aesthetic_density_and_fidelity_rules() -> None:
    assert "常规输出 40-55 个" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "最多不得超过 65 个" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "pear blossoms 不能改成 cherry blossoms" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "looking away 与 looking at viewer" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "holding sword、sword pointed at viewer" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "white five-petaled flowers" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "不要自行补充靴子、高跟鞋、袜子或腿饰" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "不要用 holding nothing" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "已经是 tags 的输入不设最低数量" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "谁对什么做了什么" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "同一语义簇最多保留 1-2 个词" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "把空出的篇幅用于具体服装结构" in DEFAULT_LLM_PROMPT_TEMPLATE
    assert "简单表情包或头像可以使用 30-45 个" in DEFAULT_LLM_PROMPT_TEMPLATE


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
