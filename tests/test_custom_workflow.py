from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from agent_tools.comfyui_workflows import custom_t2i_workflow  # noqa: E402


def test_custom_workflow_applies_generation_parameters(tmp_path: Path) -> None:
    path = tmp_path / "workflow.json"
    path.write_text(
        json.dumps(
            {
                "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
                "3": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {"width": 1024, "height": 1536, "batch_size": 1},
                },
                "4": {
                    "class_type": "KSampler",
                    "inputs": {
                        "steps": 10,
                        "cfg": 1,
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "seed": 1,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = custom_t2i_workflow(
        {
            "custom_workflow_path": str(path),
            "custom_workflow_override_parameters": True,
            "sampler_name": "er_sde",
            "scheduler": "sgm_uniform",
        },
        "new positive",
        "new negative",
        832,
        1216,
        30,
        5.0,
        42,
    )

    assert result["3"]["inputs"]["width"] == 832
    assert result["3"]["inputs"]["height"] == 1216
    assert result["4"]["inputs"]["steps"] == 30
    assert result["4"]["inputs"]["cfg"] == 5.0
    assert result["4"]["inputs"]["sampler_name"] == "er_sde"
    assert result["4"]["inputs"]["scheduler"] == "sgm_uniform"


def test_explicit_size_does_not_override_turbo_sampling_parameters(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workflow.json"
    path.write_text(
        json.dumps(
            {
                "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
                "3": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {"width": 1024, "height": 1536, "batch_size": 1},
                },
                "4": {
                    "class_type": "KSampler",
                    "inputs": {
                        "steps": 6,
                        "cfg": 1,
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "seed": 1,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = custom_t2i_workflow(
        {
            "custom_workflow_path": str(path),
            "custom_workflow_override_parameters": False,
            "sampler_name": "er_sde",
            "scheduler": "sgm_uniform",
        },
        "new positive",
        "new negative",
        1216,
        832,
        30,
        5.0,
        42,
        override_size=True,
    )

    assert result["3"]["inputs"]["width"] == 1216
    assert result["3"]["inputs"]["height"] == 832
    assert result["4"]["inputs"]["steps"] == 6
    assert result["4"]["inputs"]["cfg"] == 1
    assert result["4"]["inputs"]["sampler_name"] == "euler"
    assert result["4"]["inputs"]["scheduler"] == "normal"
