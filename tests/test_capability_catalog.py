from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from capability_catalog import CAPABILITY_ENTRIES, capability_ids, chat_actions, llm_tool_entries
from command_actions import CommandActionHandler
from llm_tool_bridge import LLMToolBridge


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


def test_capability_catalog_chat_actions_are_handled():
    handler = _handler()

    assert chat_actions() <= handler.action_names()


def test_capability_catalog_llm_tools_exist_on_bridge():
    bridge_methods = set(dir(LLMToolBridge))

    for entry in llm_tool_entries():
        assert entry.bridge_method in bridge_methods
        assert entry.llm_tool_name


def test_bridge_capability_names_match_catalog():
    bridge = LLMToolBridge(
        run_tool=lambda args: _noop_async(),
        generate=lambda event, prompt, **kwargs: _noop_async(),
        edit=lambda event, prompt: _noop_async(),
        remove_bg=lambda event: _noop_async(),
        spell=lambda event: _noop_async(),
        reverse=lambda event: _noop_async(),
    )

    assert bridge.capability_names() == capability_ids()
    assert {entry.capability_id for entry in CAPABILITY_ENTRIES} == capability_ids()
