from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
AGENT_TOOLS_DIR = PLUGIN_DIR / "agent_tools"
for path in (PLUGIN_DIR, AGENT_TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prompt_builder import build_final_prompt  # noqa: E402
from prompt_presets import (  # noqa: E402
    apply_config_preset,
    maybe_materialize_chiyo_preset,
)


def _base_config(selector: str) -> dict:
    return {
        "chiyo_preset": selector,
        "unet_name": "user-model.safetensors",
        "cfg": 6.0,
        "quality_prefix": "masterpiece, best quality, score_7, nsfw,",
        "negative_prompt": "user negative",
    }


def test_chiyo_profiles_apply_reversible_runtime_overrides() -> None:
    aesthetic = apply_config_preset(_base_config("aesthetic"))
    base = apply_config_preset(_base_config("base"))
    disabled = apply_config_preset(_base_config(""))

    aesthetic_prompt = build_final_prompt(
        user_prompt="test scene",
        llm_content="blue dress",
        config=aesthetic,
    )
    base_prompt = build_final_prompt(
        user_prompt="test scene",
        llm_content="blue dress",
        config=base,
    )

    assert aesthetic["unet_name"] == "anima_aestheticV11.safetensors"
    assert aesthetic["cfg"] == 3.0
    assert aesthetic["negative_prompt"] == ""
    assert not aesthetic_prompt.final_prompt.startswith("masterpiece")

    assert base["unet_name"] == "anima_baseV10.safetensors"
    assert base["cfg"] == 5.0
    assert base["negative_prompt"] == "user negative"
    assert base_prompt.final_prompt.startswith(
        "masterpiece, best quality, score_7, nsfw"
    )

    assert disabled["unet_name"] == "user-model.safetensors"
    assert disabled["cfg"] == 6.0
    assert disabled["negative_prompt"] == "user negative"
    assert "preset_suppress_quality" not in disabled


def test_legacy_chiyo_switch_migrates_without_overwriting_base_config() -> None:
    legacy = _base_config("")
    legacy["chiyo_preset_enabled"] = True

    migrated = maybe_materialize_chiyo_preset(None, base_config=legacy)

    assert migrated["chiyo_preset"] == "base"
    assert "chiyo_preset_enabled" not in migrated
    assert "preset_profile" not in migrated
    assert "preset_suppress_quality" not in migrated
    for key in ("unet_name", "cfg", "quality_prefix", "negative_prompt"):
        assert migrated[key] == legacy[key]


def test_comfyui_helper_uses_effective_profile_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import comfyui_agent

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "anima_master_basic": {"chiyo_preset": "aesthetic"},
                "anima_master_models": {
                    "unet_name": "user-model.safetensors",
                },
                "anima_master_rendering": {"cfg": 6.0},
                "anima_master_default_prompt": {
                    "negative_prompt": "user negative",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(comfyui_agent, "CONFIG", config_path)

    effective = comfyui_agent.load_config()

    assert effective["unet_name"] == "anima_aestheticV11.safetensors"
    assert effective["cfg"] == 3.0
    assert effective["negative_prompt"] == ""
