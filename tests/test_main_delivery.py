from __future__ import annotations

import asyncio
from pathlib import Path
import sys

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from main import ComfyUIAgentPlugin  # noqa: E402


def test_generate_notifies_user_when_prompt_optimization_degrades() -> None:
    class _Event:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def plain_result(self, text: str) -> str:
            return text

        async def send(self, result: str) -> None:
            self.messages.append(result)

    class _Task:
        def record_delivery(self, task_id, delivery) -> None:
            self.recorded = (task_id, delivery)

    plugin = ComfyUIAgentPlugin.__new__(ComfyUIAgentPlugin)
    payload = {
        "ok": True,
        "task_id": "task",
        "prompt_degraded": True,
        "delivery": {"status": "sent"},
    }

    async def generate_payload(*_args, **_kwargs):
        return payload

    async def send_payload(_event, _payload):
        return "sent"

    plugin._generate_payload = generate_payload
    plugin._send_payload = send_payload
    plugin._generation_task = _Task()
    event = _Event()

    result = asyncio.run(plugin._generate(event, "画一个女孩"))

    assert result == "sent"
    assert len(event.messages) == 1
    assert "提示词优化服务不可用" in event.messages[0]
