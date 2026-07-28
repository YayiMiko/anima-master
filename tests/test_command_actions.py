from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from command_actions import CommandActionHandler  # noqa: E402
from command_catalog import COMMAND_ENTRIES  # noqa: E402
from multi_person_prompt import MULTI_PERSON_NEGATIVE_TAGS  # noqa: E402
from prompt_presets import DEFAULT_NEGATIVE_PROMPT  # noqa: E402


class _Recorder:
    def debug_status_text(self, config):
        return "debug"


def _noop_async(*args, **kwargs):
    async def _inner():
        return "ok"

    return _inner()


def _handler(config=None, generate=None) -> CommandActionHandler:
    return CommandActionHandler(
        config=config or {},
        task_recorder=_Recorder(),
        reference_context=None,
        is_allowed=lambda event: True,
        run_tool=lambda args: _noop_async(),
        ensure_ready=lambda event: _noop_async(),
        send_payload=lambda event, payload: _noop_async(),
        generate=generate or (lambda event, prompt, **kwargs: _noop_async()),
        event_image_input=lambda event: _noop_async(),
        build_prompt=lambda event, prompt, mode="txt2img": _noop_async(),
        format_spell_payload=lambda payload: "spell",
        get_bool=lambda key, default: default,
        shorten=lambda text, limit: text[:limit],
        config_store=None,
    )


def test_action_dispatch_covers_catalog_actions():
    handler = _handler()
    catalog_actions = {
        entry.action for entry in COMMAND_ENTRIES if entry.action != "raw_generate"
    }

    assert catalog_actions <= handler.action_names()


def test_unknown_action_returns_error():
    handler = _handler()

    result = asyncio.run(handler.handle_action(object(), "nope", ""))
    assert result == "未知 Anima 指令。"


def test_generate_action_passes_one_time_size_override():
    calls = []

    async def generate(event, prompt, **kwargs):
        calls.append((prompt, kwargs))

    handler = _handler(
        config={"allowed_sizes": ["1024x1024", "1216x832"]},
        generate=generate,
    )

    result = asyncio.run(
        handler.handle_action(object(), "generate", "横图：少女站在河岸")
    )

    assert result is None
    assert calls == [("少女站在河岸", {"width": 1216, "height": 832})]


def test_generate_action_rejects_unavailable_size_before_generation():
    calls = []

    async def generate(event, prompt, **kwargs):
        calls.append((prompt, kwargs))

    handler = _handler(
        config={"allowed_sizes": ["1024x1024"]},
        generate=generate,
    )

    result = asyncio.run(handler.handle_action(object(), "generate", "1000x1400：少女"))

    assert result == "尺寸 1000x1400 不可用。可用尺寸：1024x1024"
    assert calls == []


def test_multi_person_action_uses_horizontal_default_and_request_flag():
    calls = []

    async def generate(event, prompt, **kwargs):
        calls.append((prompt, kwargs))

    handler = _handler(
        config={"allowed_sizes": ["1024x1024", "1216x832", "832x1216"]},
        generate=generate,
    )

    result = asyncio.run(
        handler.handle_action(
            object(),
            "multi_person",
            "左边若叶睦，右边千早爱音，两人牵手",
        )
    )

    assert result is None
    assert calls == [
        (
            "左边若叶睦，右边千早爱音，两人牵手",
            {
                "width": 1216,
                "height": 832,
                "negative_prompt": (
                    f"{DEFAULT_NEGATIVE_PROMPT}, "
                    f"{', '.join(MULTI_PERSON_NEGATIVE_TAGS)}"
                ),
                "multi_person": True,
            },
        )
    ]


def test_multi_person_action_preserves_explicit_vertical_size():
    calls = []

    async def generate(event, prompt, **kwargs):
        calls.append((prompt, kwargs))

    handler = _handler(
        config={"allowed_sizes": ["1216x832", "832x1216"]},
        generate=generate,
    )

    result = asyncio.run(
        handler.handle_action(
            object(),
            "multi_person",
            "竖图：前景一个女孩，背景一个男孩",
        )
    )

    assert result is None
    assert calls == [
        (
            "前景一个女孩，背景一个男孩",
            {
                "width": 832,
                "height": 1216,
                "negative_prompt": (
                    f"{DEFAULT_NEGATIVE_PROMPT}, "
                    f"{', '.join(MULTI_PERSON_NEGATIVE_TAGS)}"
                ),
                "multi_person": True,
            },
        )
    ]
