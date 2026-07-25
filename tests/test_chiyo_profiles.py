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
    CHIYO_BASE_CONFIG_SNAPSHOT_KEY,
    CHIYO_VISIBLE_OVERRIDE_KEYS,
    apply_config_preset,
    artist_presets,
    maybe_materialize_chiyo_preset,
)


def _base_config(selector: str) -> dict:
    return {
        "chiyo_preset": selector,
        "unet_name": "user-model.safetensors",
        "clip_name": "user-clip.safetensors",
        "vae_name": "user-vae.safetensors",
        "steps": 28,
        "cfg": 6.0,
        "sampler_name": "user_sampler",
        "scheduler": "user_scheduler",
        "quality_prefix": "masterpiece, best quality, score_7, nsfw,",
        "negative_prompt": "user negative",
        "custom_workflow_enabled": False,
        "custom_workflow_path": "user-workflow.json",
        "custom_workflow_override_parameters": True,
    }


def test_chiyo_profiles_apply_reversible_runtime_overrides() -> None:
    aesthetic = apply_config_preset(_base_config("aesthetic"))
    base = apply_config_preset(_base_config("base"))
    turbo = apply_config_preset(_base_config("turbo"))
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

    assert turbo["unet_name"] == "anima_baseV10.safetensors"
    assert turbo["clip_name"] == "qwen_3_06b_base.safetensors"
    assert turbo["vae_name"] == "qwen_image_vae.safetensors"
    assert turbo["steps"] == 10
    assert turbo["cfg"] == 1.0
    assert turbo["sampler_name"] == "euler"
    assert turbo["scheduler"] == "simple"
    assert turbo["custom_workflow_enabled"] is True
    assert turbo["custom_workflow_override_parameters"] is False
    assert turbo["custom_workflow_path"].endswith("comfyui_00051_api.json")
    assert turbo["low_cfg_harness_enabled"] is True
    assert turbo["active_artist_preset"] == "千代turbo"
    assert "anime coloring" in artist_presets(turbo)["千代turbo"]

    assert disabled["unet_name"] == "user-model.safetensors"
    assert disabled["cfg"] == 6.0
    assert disabled["negative_prompt"] == "user negative"
    assert "preset_suppress_quality" not in disabled


def test_legacy_chiyo_switch_migrates_and_keeps_recovery_snapshot(
    tmp_path: Path,
) -> None:
    legacy = _base_config("")
    legacy["chiyo_preset_enabled"] = True
    snapshot_path = tmp_path / "chiyo_preset_base.json"

    migrated = maybe_materialize_chiyo_preset(
        None,
        base_config=legacy,
        snapshot_path=snapshot_path,
    )

    assert migrated["chiyo_preset"] == "base"
    assert "chiyo_preset_enabled" not in migrated
    assert "preset_profile" not in migrated
    assert "preset_suppress_quality" not in migrated
    assert migrated["unet_name"] == "anima_baseV10.safetensors"
    assert migrated["cfg"] == 5.0
    assert migrated["quality_prefix"] == legacy["quality_prefix"]
    assert migrated["negative_prompt"] == legacy["negative_prompt"]
    assert CHIYO_BASE_CONFIG_SNAPSHOT_KEY not in migrated
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    for key in CHIYO_VISIBLE_OVERRIDE_KEYS:
        assert snapshot[key] == legacy[key]


def test_materialized_profile_fields_switch_and_restore_visibly(
    tmp_path: Path,
) -> None:
    original = _base_config("aesthetic")
    snapshot_path = tmp_path / "chiyo_preset_base.json"

    aesthetic = maybe_materialize_chiyo_preset(
        None,
        base_config=original,
        snapshot_path=snapshot_path,
    )
    assert aesthetic["unet_name"] == "anima_aestheticV11.safetensors"
    assert aesthetic["cfg"] == 3.0
    assert aesthetic["quality_prefix"] == ""
    assert aesthetic["negative_prompt"] == ""

    aesthetic["chiyo_preset"] = "turbo"
    turbo = maybe_materialize_chiyo_preset(
        None,
        base_config=aesthetic,
        snapshot_path=snapshot_path,
    )
    assert turbo["unet_name"] == "anima_baseV10.safetensors"
    assert turbo["steps"] == 10
    assert turbo["cfg"] == 1.0
    assert turbo["sampler_name"] == "euler"
    assert turbo["scheduler"] == "simple"
    assert turbo["quality_prefix"] == original["quality_prefix"]
    assert turbo["negative_prompt"] == original["negative_prompt"]

    turbo["chiyo_preset"] = ""
    restored = maybe_materialize_chiyo_preset(
        None,
        base_config=turbo,
        snapshot_path=snapshot_path,
    )
    for key in CHIYO_VISIBLE_OVERRIDE_KEYS:
        assert restored[key] == original[key]
    assert CHIYO_BASE_CONFIG_SNAPSHOT_KEY not in restored
    assert not snapshot_path.exists()


def test_visible_inline_snapshot_migrates_to_plugin_data(tmp_path: Path) -> None:
    original = _base_config("aesthetic")
    current = dict(original)
    current.update(
        {
            "unet_name": "anima_aestheticV11.safetensors",
            "cfg": 3.0,
            "quality_prefix": "",
            "negative_prompt": "",
            CHIYO_BASE_CONFIG_SNAPSHOT_KEY: {
                key: original[key] for key in CHIYO_VISIBLE_OVERRIDE_KEYS
            },
        }
    )
    snapshot_path = tmp_path / "chiyo_preset_base.json"

    migrated = maybe_materialize_chiyo_preset(
        None,
        base_config=current,
        snapshot_path=snapshot_path,
    )

    assert CHIYO_BASE_CONFIG_SNAPSHOT_KEY not in migrated
    assert snapshot_path.exists()
    assert migrated["unet_name"] == "anima_aestheticV11.safetensors"
    assert migrated["cfg"] == 3.0
    saved = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert saved["unet_name"] == "user-model.safetensors"
    assert saved["cfg"] == 6.0


def test_turbo_profile_preserves_saved_chiyo_artist_groups(tmp_path: Path) -> None:
    config = _base_config("turbo")
    config.update(
        {
            "artist_presets": [
                "千代风格=@legacy,",
                "千代turbo=@custom_turbo,",
                "千代turbo2=@custom_turbo_2,",
            ],
            "active_artist_preset": "千代风格",
        }
    )

    materialized = maybe_materialize_chiyo_preset(
        None,
        base_config=config,
        snapshot_path=tmp_path / "chiyo_preset_base.json",
    )
    presets = artist_presets(materialized)

    assert materialized["active_artist_preset"] == "千代turbo"
    assert presets["千代turbo"] == "@custom_turbo,"
    assert presets["千代turbo2"] == "@custom_turbo_2,"
    assert presets["千代base"] == "@legacy,"


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


def test_agent_tools_find_astrbot_root_from_runtime_working_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import comfyui_agent
    import image_prompt_agent

    (tmp_path / "astrbot").mkdir()
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)

    assert comfyui_agent._find_astrbot_root() == tmp_path
    assert image_prompt_agent._find_astrbot_root() == tmp_path
