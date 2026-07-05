from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from command_actions import CommandActionHandler
from command_catalog import COMMAND_ENTRIES


class _Recorder:
    def debug_status_text(self, config):
        return "debug"


def _noop_async(*args, **kwargs):
    async def _inner():
        return "ok"

    return _inner()


def _handler() -> CommandActionHandler:
    return CommandActionHandler(
        config={},
        task_recorder=_Recorder(),
        reference_context=None,
        is_allowed=lambda event: True,
        run_tool=lambda args: _noop_async(),
        ensure_ready=lambda event: _noop_async(),
        send_payload=lambda event, payload: _noop_async(),
        generate=lambda event, prompt, **kwargs: _noop_async(),
        event_image_input=lambda event: _noop_async(),
        build_prompt=lambda event, prompt, mode="txt2img": _noop_async(),
        format_spell_payload=lambda payload: "spell",
        get_bool=lambda key, default: default,
        shorten=lambda text, limit: text[:limit],
        config_store=None,
    )


def test_action_dispatch_covers_catalog_actions():
    handler = _handler()
    catalog_actions = {entry.action for entry in COMMAND_ENTRIES if entry.action != "raw_generate"}

    assert catalog_actions <= handler.action_names()


def test_unknown_action_returns_error():
    handler = _handler()

    import asyncio

    result = asyncio.run(handler.handle_action(object(), "nope", ""))
    assert result == "未知 Anima 指令。"
