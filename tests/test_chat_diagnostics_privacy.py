from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from deployment_diagnostics import compact_status_text, diagnostic_text  # noqa: E402
from llm_tool_bridge import LLMToolBridge  # noqa: E402
from task_state import TaskRecorder  # noqa: E402
from task_summary import build_last_task_debug_lines  # noqa: E402


PRIVATE_URL = "http://100.68.56.22:8188"
PRIVATE_PATH = r"C:\Users\Admin\Pictures\secret.png"


def test_chat_status_and_diagnostics_hide_private_details(tmp_path: Path):
    payload = {
        "ok": False,
        "base_url": PRIVATE_URL,
        "error": f"ConnectionError: {PRIVATE_URL} {PRIVATE_PATH}",
        "connection_issue": "remote_connection_failed",
        "connection_hint": f"Check {PRIVATE_URL}",
        "dns_checks": {"private.example": False},
    }
    last_task = {
        "error": f"Failed at {PRIVATE_PATH}",
        "delivery": {"error": PRIVATE_URL, "status": "failed"},
    }
    image_input = {
        "path": PRIVATE_PATH,
        "original_name": "secret.png",
        "label": "private.example",
        "direct_images": 1,
    }

    text = "\n".join(
        [
            compact_status_text(payload),
            diagnostic_text(payload, {}, last_task, image_input),
            TaskRecorder(tmp_path / "last_task.json", None).debug_status_text(
                {"comfyui_base_url": PRIVATE_URL, "custom_workflow_path": PRIVATE_PATH}
            ),
        ]
    )
    for private_value in (PRIVATE_URL, PRIVATE_PATH, "secret.png", "private.example"):
        assert private_value not in text
    assert "连接失败" in text
    assert "图片：已找到" in text


def test_latest_task_debug_hides_errors_and_user_content():
    text = "\n".join(
        build_last_task_debug_lines(
            {
                "error": f"Failed at {PRIVATE_PATH}",
                "strategy_summary": {
                    "fixed_character_name": "private.example",
                    "character_slots": [PRIVATE_URL],
                },
                "prompt_summary": {
                    "stage_events": [
                        {
                            "stage": "provider",
                            "status": "failed",
                            "reason": PRIVATE_PATH,
                        }
                    ]
                },
            }
        )
    )
    for private_value in (PRIVATE_URL, PRIVATE_PATH, "private.example"):
        assert private_value not in text


def test_llm_status_tool_uses_private_safe_status():
    async def run_tool(_args):
        return {"ok": False, "error": f"Failed to connect to {PRIVATE_URL}"}

    bridge = LLMToolBridge(
        run_tool=run_tool,
        generate=None,
        edit=None,
        remove_bg=None,
        spell=None,
        reverse=None,
    )
    text = asyncio.run(bridge.status(None))
    assert PRIVATE_URL not in text
    assert "状态检查失败" in text
