from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from config_defaults import migrate_prompt_defaults  # noqa: E402
from prompt_templates import DEFAULT_LLM_PROMPT_TEMPLATE  # noqa: E402


def test_empty_builtin_prompt_fields_migrate_to_aesthetic_defaults() -> None:
    migrated = migrate_prompt_defaults(
        {
            "prompt_builder_template": "",
            "prompt_builder_max_content_tags": 80,
        }
    )

    assert migrated["prompt_builder_template"] == DEFAULT_LLM_PROMPT_TEMPLATE
    assert migrated["prompt_builder_max_content_tags"] == 65


def test_custom_prompt_template_and_limit_are_preserved() -> None:
    migrated = migrate_prompt_defaults(
        {
            "prompt_builder_template": "我的自定义模板：{theme}",
            "prompt_builder_max_content_tags": 72,
        }
    )

    assert migrated["prompt_builder_template"] == "我的自定义模板：{theme}"
    assert migrated["prompt_builder_max_content_tags"] == 72
