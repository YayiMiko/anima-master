from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from generation_verifier import GenerationVerifier  # noqa: E402


class _Context:
    def __init__(self):
        self.calls = []

    async def llm_generate(self, **kwargs):
        self.calls.append(kwargs)
        return type("_Response", (), {"completion_text": "{}"})()


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


def _verifier(context: _Context) -> GenerationVerifier:
    return GenerationVerifier(
        context=context,
        task_recorder=object(),
        generate_payload=lambda *args, **kwargs: None,
        logger=_Logger(),
        get_bool=lambda key, default: default,
        get_int=lambda key, default: default,
        get_str=lambda key, default: default,
    )


def test_multi_person_verification_adds_multi_only_checks() -> None:
    context = _Context()
    verifier = _verifier(context)

    asyncio.run(
        verifier._make_verify_llm_call("provider", multi_person=True)("verify")
    )

    system_prompt = context.calls[0]["system_prompt"]
    assert "/anm 多人" in system_prompt
    assert "分屏" in system_prompt
    assert "额外人物" in system_prompt
    assert "互动的主动方" in system_prompt


def test_ordinary_verification_does_not_receive_multi_person_checks() -> None:
    context = _Context()
    verifier = _verifier(context)

    asyncio.run(
        verifier._make_verify_llm_call("provider", multi_person=False)("verify")
    )

    system_prompt = context.calls[0]["system_prompt"]
    assert "/anm 多人" not in system_prompt
    assert "互动的主动方" not in system_prompt


def test_multi_person_verification_is_forced_when_global_verify_is_disabled():
    class _Recorder:
        def __init__(self):
            self.written = []

        def read(self, task_id):
            return {"task_id": task_id}

        def write(self, task):
            self.written.append(task)

    context = _Context()
    recorder = _Recorder()
    verifier = GenerationVerifier(
        context=context,
        task_recorder=recorder,
        generate_payload=lambda *args, **kwargs: None,
        logger=_Logger(),
        get_bool=lambda key, default: False,
        get_int=lambda key, default: default,
        get_str=lambda key, default: default,
    )

    asyncio.run(
        verifier.verify_and_maybe_retry(
            object(),
            {"task_id": "task", "ok": False},
            user_request="two people",
            width=1216,
            height=832,
            steps=30,
            cfg=5.0,
            negative_prompt=None,
            multi_person=True,
        )
    )

    verification = recorder.written[0]["verification_summary"]
    assert verification["enabled"] is True
    assert verification["forced_multi_person"] is True
    assert verification["skip_reason"] == "generation_failed"
