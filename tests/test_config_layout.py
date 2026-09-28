from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from anima.runtime.config_defaults import (  # noqa: E402
    group_config,
    maybe_reset_to_defaults,
)


def test_default_config_page_keeps_common_sections_visible() -> None:
    schema = json.loads((PLUGIN_DIR / "_conf_schema.json").read_text(encoding="utf-8"))
    basic = schema["anima_master_basic"]["items"]

    assert list(basic) == [
        "chiyo_preset",
        "show_advanced_settings",
        "reset_to_defaults",
    ]
    assert basic["show_advanced_settings"]["default"] is False
    common = {
        "anima_master_basic",
        "anima_master_comfyui_connection",
        "anima_master_models",
        "anima_master_rendering",
    }
    for key, section in schema.items():
        if key not in common:
            assert (
                section["condition"]["anima_master_basic.show_advanced_settings"]
                is True
            )
        else:
            assert "anima_master_basic.show_advanced_settings" not in section.get(
                "condition", {}
            )

    assert (
        schema["anima_master_models"]["condition"][
            "anima_master_comfyui_connection.custom_workflow_enabled"
        ]
        is False
    )
    assert (
        schema["anima_master_rendering"]["condition"][
            "anima_master_comfyui_connection.custom_workflow_enabled"
        ]
        is False
    )


def test_existing_grouped_values_stay_in_original_sections() -> None:
    previous = {
        "anima_master_basic": {"chiyo_preset": "aesthetic", "reset_to_defaults": False},
        "anima_master_comfyui_connection": {
            "comfyui_base_url": "http://example.test:8188",
            "custom_workflow_enabled": True,
            "custom_workflow_path": "custom.json",
        },
        "anima_master_rendering": {"width": 1216, "height": 832, "cfg": 3.5},
        "anima_master_style": {
            "active_artist_preset": "my artist",
            "active_style_preset": "my style",
            "artist_presets": ["my artist=artist tag"],
        },
        "anima_master_multi_person": {"multi_candidate_count": 3},
    }

    grouped = group_config(previous, PLUGIN_DIR / "_conf_schema.json")

    assert (
        grouped["anima_master_comfyui_connection"]["comfyui_base_url"]
        == "http://example.test:8188"
    )
    assert grouped["anima_master_rendering"]["width"] == 1216
    assert grouped["anima_master_rendering"]["height"] == 832
    assert grouped["anima_master_style"]["active_artist_preset"] == "my artist"
    assert grouped["anima_master_style"]["active_style_preset"] == "my style"
    assert grouped["anima_master_basic"]["show_advanced_settings"] is False
    assert grouped["anima_master_basic"]["reset_to_defaults"] is False
    assert (
        grouped["anima_master_comfyui_connection"]["custom_workflow_path"]
        == "custom.json"
    )
    assert grouped["anima_master_rendering"]["cfg"] == 3.5
    assert grouped["anima_master_style"]["artist_presets"] == ["my artist=artist tag"]
    assert grouped["anima_master_multi_person"]["multi_candidate_count"] == 3


def test_reset_switch_works_from_basic_section() -> None:
    schema_path = PLUGIN_DIR / "_conf_schema.json"
    reset = maybe_reset_to_defaults(
        {"anima_master_basic": {"reset_to_defaults": True, "width": 2048}},
        schema_path,
    )

    assert reset["reset_to_defaults"] is False
    assert reset["width"] == 1024
    assert reset["show_advanced_settings"] is False
