from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import generation_verifier as verifier_module  # noqa: E402
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

    asyncio.run(verifier._make_verify_llm_call("provider", multi_person=True)("verify"))

    system_prompt = context.calls[0]["system_prompt"]
    assert "/anm 多人" in system_prompt
    assert "分屏" in system_prompt
    assert "额外人物" in system_prompt
    assert "互动的主动方" in system_prompt
    assert "multi_facts" in system_prompt
    assert "visible_person_count" in system_prompt


def test_ordinary_verification_does_not_receive_multi_person_checks() -> None:
    context = _Context()
    verifier = _verifier(context)

    asyncio.run(
        verifier._make_verify_llm_call("provider", multi_person=False)("verify")
    )

    system_prompt = context.calls[0]["system_prompt"]
    assert "/anm 多人" not in system_prompt
    assert "互动的主动方" not in system_prompt


def test_named_character_verification_adds_identity_checks() -> None:
    context = _Context()
    verifier = _verifier(context)

    asyncio.run(
        verifier._make_verify_llm_call(
            "provider",
            character_identity=("example_(work): blue hair, blue eyes, long hair"),
        )("verify")
    )

    system_prompt = context.calls[0]["system_prompt"]
    assert "现有作品角色" in system_prompt
    assert "标志性的发色、瞳色、发型" in system_prompt
    assert "example_(work): blue hair, blue eyes, long hair" in system_prompt


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
        get_bool=lambda key, default: False if key == "enable_verify" else default,
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


def test_named_character_verification_is_forced_when_global_verify_is_disabled():
    class _Recorder:
        def __init__(self):
            self.written = []

        def read(self, task_id):
            return {
                "task_id": task_id,
                "prompt_summary": {
                    "named_character_detected": True,
                    "character_canonical_tag": "example_(work)",
                    "character_identity_tags": [
                        "example_(work)",
                        "blue hair",
                        "blue eyes",
                    ],
                },
            }

        def write(self, task):
            self.written.append(task)

    recorder = _Recorder()
    verifier = GenerationVerifier(
        context=_Context(),
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
            user_request="named character",
            width=1024,
            height=1536,
            steps=30,
            cfg=5.0,
            negative_prompt=None,
        )
    )

    verification = recorder.written[0]["verification_summary"]
    assert verification["enabled"] is True
    assert verification["forced_named_character"] is True
    assert verification["skip_reason"] == "generation_failed"


def test_multi_person_retry_reuses_plan_and_blocks_persistent_failure(monkeypatch):
    class _Recorder:
        def __init__(self):
            self.written = []

        def read(self, task_id):
            return {
                "task_id": task_id,
                "prompt_summary": {"multi_person_mode": True},
            }

        def write(self, task):
            self.written.append(task)

    retry_calls = []

    async def generate_payload(event, prompt, **kwargs):
        retry_calls.append((prompt, kwargs))
        attempt = len(retry_calls)
        return {
            "task_id": f"retry-{attempt}",
            "ok": True,
            "outputs": [f"retry-{attempt}.png"],
            "_prepared_prompt": kwargs.get("prepared_prompt"),
            "_prepared_prompt_summary": kwargs.get("prepared_prompt_summary"),
        }

    async def failed_verdict(*args, **kwargs):
        return verifier_module.anima_verify.Verdict(
            passed=False,
            score=3,
            issues=["split screen"],
            fix_hint="keep one continuous scene",
        )

    monkeypatch.setattr(verifier_module.anima_verify, "verify_image", failed_verdict)
    recorder = _Recorder()
    verifier = GenerationVerifier(
        context=_Context(),
        task_recorder=recorder,
        generate_payload=generate_payload,
        logger=_Logger(),
        get_bool=lambda key, default: True,
        get_int=lambda key, default: (
            3
            if key == "multi_candidate_count"
            else 1
            if key == "max_verify_retry"
            else default
        ),
        get_str=lambda key, default: (
            "provider" if key == "verify_provider_id" else default
        ),
    )

    outcome = asyncio.run(
        verifier.verify_and_maybe_retry(
            object(),
            {
                "task_id": "initial",
                "ok": True,
                "outputs": ["initial.png"],
                "_prepared_prompt": "validated structured prompt",
                "_prepared_prompt_summary": {"multi_person_mode": True},
            },
            user_request="two characters embracing",
            width=1024,
            height=1024,
            steps=30,
            cfg=5.0,
            negative_prompt="split screen",
            multi_person=True,
        )
    )

    assert len(retry_calls) == 2
    assert all(prompt == "two characters embracing" for prompt, _ in retry_calls)
    assert all(
        kwargs["prepared_prompt"].startswith("validated structured prompt")
        for _, kwargs in retry_calls
    )
    assert outcome.payload["ok"] is True
    assert outcome.payload["selected_output_path"] == "initial.png"
    assert outcome.payload["verification_warning"] == "multi_person_verification_failed"
    verification = recorder.written[-1]["verification_summary"]
    assert verification["max_retry"] == 2
    assert verification["final_passed"] is False
    assert verification["degraded_delivery"] is True
    assert verification["selection_policy"] == "best_available_candidate"


def test_multi_person_facts_are_parsed_without_overriding_the_pass_flag():
    async def llm_call(**kwargs):
        return (
            '{"score": 8, "pass": true, "issues": [], "fix_hint": "", '
            '"multi_facts": {"visible_person_count": 2, '
            '"layout": "single_scene", "identity_match": "partial", '
            '"interaction_direction": "correct"}}'
        )

    verdict = asyncio.run(
        verifier_module.anima_verify.verify_image(
            llm_call,
            "image.png",
            "two characters",
            require_facts=True,
        )
    )

    assert verdict.passed is True
    assert verdict.visible_person_count == 2
    assert verdict.layout == "single_scene"
    assert verdict.identity_match == "partial"


def test_multi_person_selects_best_earlier_candidate(monkeypatch):
    class _Recorder:
        def __init__(self):
            self.written = []

        def read(self, task_id):
            return {
                "task_id": task_id,
                "prompt_summary": {
                    "multi_person_mode": True,
                    "planned_character_count": 2,
                },
            }

        def write(self, task):
            self.written.append(task)

    verdicts = iter(
        (
            verifier_module.anima_verify.Verdict(
                passed=False,
                score=9,
                visible_person_count=4,
                layout="collage",
            ),
            verifier_module.anima_verify.Verdict(
                passed=False,
                score=6,
                visible_person_count=2,
                layout="single_scene",
                identity_match="partial",
                interaction_direction="correct",
            ),
            verifier_module.anima_verify.Verdict(
                passed=False,
                score=8,
                visible_person_count=3,
                layout="single_scene",
                identity_match="correct",
                interaction_direction="correct",
            ),
        )
    )

    async def verify_image(*args, **kwargs):
        return next(verdicts)

    retry_calls = []

    async def generate_payload(event, prompt, **kwargs):
        retry_calls.append((prompt, kwargs))
        attempt = len(retry_calls) + 1
        return {
            "task_id": f"candidate-{attempt}",
            "ok": True,
            "outputs": [f"candidate-{attempt}.png"],
        }

    monkeypatch.setattr(verifier_module.anima_verify, "verify_image", verify_image)
    recorder = _Recorder()
    verifier = GenerationVerifier(
        context=_Context(),
        task_recorder=recorder,
        generate_payload=generate_payload,
        logger=_Logger(),
        get_bool=lambda key, default: True,
        get_int=lambda key, default: (
            3 if key == "multi_candidate_count" else default
        ),
        get_str=lambda key, default: (
            "provider" if key == "verify_provider_id" else default
        ),
    )

    outcome = asyncio.run(
        verifier.verify_and_maybe_retry(
            object(),
            {
                "task_id": "candidate-1",
                "ok": True,
                "outputs": ["candidate-1.png"],
                "_prepared_prompt": "compact prompt",
                "_prepared_prompt_summary": {"planned_character_count": 2},
            },
            user_request="two people",
            width=1024,
            height=1024,
            steps=30,
            cfg=5.0,
            negative_prompt=None,
            multi_person=True,
        )
    )

    assert outcome.payload["task_id"] == "candidate-2"
    assert outcome.payload["ok"] is True
    assert outcome.payload["selected_output_path"] == "candidate-2.png"
    assert all(
        kwargs["prepared_prompt"] == "compact prompt" for _, kwargs in retry_calls
    )
    verification = recorder.written[-1]["verification_summary"]
    assert verification["candidate_count"] == 3
    assert verification["eligible_candidate_count"] == 1
    assert verification["selected_attempt"] == 2


def test_multi_person_low_confidence_identity_error_is_not_a_hard_failure():
    verdict = verifier_module.anima_verify.Verdict(
        passed=True,
        score=7,
        visible_person_count=2,
        layout="single_scene",
        identity_match="wrong",
        identity_confidence=0.35,
        interaction_direction="correct",
        direction_confidence=0.9,
    )

    eligible, rank = GenerationVerifier._multi_candidate_rank(verdict, 2)

    assert eligible is True
    assert rank > 150


def test_multi_person_missing_facts_retries_only_the_vision_call():
    replies = iter(
        (
            '{"score": 7, "pass": true, "issues": [], "fix_hint": ""}',
            '{"score": 7, "pass": true, "issues": [], "fix_hint": "", '
            '"multi_facts": {"visible_person_count": 2, '
            '"layout": "single_scene", "identity_match": "correct", '
            '"interaction_direction": "correct"}}',
        )
    )
    calls = []

    async def llm_call(**kwargs):
        calls.append(kwargs)
        return next(replies)

    verdict = asyncio.run(
        verifier_module.anima_verify.verify_image(
            llm_call,
            "image.png",
            "two people",
            require_facts=True,
        )
    )

    assert len(calls) == 2
    assert verdict.visible_person_count == 2
