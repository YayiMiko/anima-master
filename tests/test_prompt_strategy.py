from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from prompt_pipeline import PromptPipeline  # noqa: E402
from prompt_presets import looks_like_danbooru_tags  # noqa: E402
from task_summary import (  # noqa: E402
    apply_verification_summary,
    build_last_task_debug_lines,
    build_strategy_summary,
)


def _shorten(text: str, limit: int = 600) -> str:
    return text[:limit]


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


def _pipeline(config: dict | None = None) -> PromptPipeline:
    config = dict(config or {})
    return PromptPipeline(
        context=None,
        config=config,
        logger=_Logger(),
        danbooru_resolver=None,
        researcher=None,
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=_shorten,
    )


def test_prompt_pipeline_refills_details_after_semantic_deduplication():
    class _Response:
        def __init__(self, text: str):
            self.completion_text = text

    class _Context:
        def __init__(self):
            self.outputs = [
                ", ".join(
                    [f"scene detail {index}" for index in range(40)]
                    + [
                        "light rays",
                        "sunbeams",
                        "glowing",
                        "illuminated",
                        "bright",
                        "luminous",
                        "radiant",
                        "floating particles",
                        "light particles",
                    ]
                ),
                ", ".join(
                    [f"scene detail {index}" for index in range(40)]
                    + [f"refined visual detail {index}" for index in range(8)]
                ),
            ]

        async def get_current_chat_provider_id(self, umo):
            return "provider"

        async def llm_generate(self, **kwargs):
            return _Response(self.outputs.pop(0))

    class _Plan:
        use_web_search = False
        use_deep_thinking = False
        search_reason = ""
        thinking_reason = ""

    class _Researcher:
        def plan(self, prompt):
            return _Plan()

    class _Resolver:
        def required_core_tags_for_prompt(self, prompt):
            return ()

        async def resolve(self, *, llm_content, user_prompt, fixed_character):
            return llm_content

    class _Event:
        unified_msg_origin = "session"

    context = _Context()
    config = {"chiyo_preset_enabled": False}
    pipeline = PromptPipeline(
        context=context,
        config=config,
        logger=_Logger(),
        danbooru_resolver=_Resolver(),
        researcher=_Researcher(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=_shorten,
    )

    result = asyncio.run(pipeline.build(_Event(), "女孩在晨光中伸手"))

    assert result.summary["detail_refill_attempted"] is True
    assert result.summary["detail_refill_retry"] is True
    assert result.summary["short_content_retry"] is False
    assert result.summary["removed_content_tag_count"] == 0
    assert result.summary["llm_content_tag_count"] == 48
    assert "refined visual detail 7" in result.final_prompt
    assert context.outputs == []


def test_prompt_pipeline_creative_expansion_strips_flag_and_enriches_tags():
    class _Response:
        def __init__(self, text: str):
            self.completion_text = text

    class _Context:
        def __init__(self):
            self.calls = []

        async def get_current_chat_provider_id(self, umo):
            return "provider"

        async def llm_generate(self, **kwargs):
            self.calls.append(kwargs)
            return _Response(
                ", ".join(f"creative visual detail {index}" for index in range(52))
            )

    class _Plan:
        use_web_search = False
        use_deep_thinking = False
        search_reason = ""
        thinking_reason = ""

    class _Researcher:
        def plan(self, prompt):
            return _Plan()

    class _Resolver:
        def required_core_tags_for_prompt(self, prompt):
            return ()

        async def resolve(self, *, llm_content, user_prompt, fixed_character):
            return llm_content

    class _Event:
        unified_msg_origin = "session"

    context = _Context()
    config = {"chiyo_preset_enabled": False}
    pipeline = PromptPipeline(
        context=context,
        config=config,
        logger=_Logger(),
        danbooru_resolver=_Resolver(),
        researcher=_Researcher(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=_shorten,
    )

    result = asyncio.run(
        pipeline.build(
            _Event(),
            "1girl, solo, traveling magical girl, white dress, simple background --自由发挥",
        )
    )

    assert result.summary["creative_expansion"] is True
    assert result.summary.get("danbooru_fast_path") is not True
    assert result.summary["llm_content_tag_count"] == 52
    assert "--自由发挥" not in result.final_prompt
    assert len(context.calls) == 1
    assert "本次启用“自由发挥”模式" in context.calls[0]["prompt"]
    assert "本次启用自由发挥模式" in context.calls[0]["system_prompt"]
    assert "场景类Tag门控" not in context.calls[0]["system_prompt"]


def test_danbooru_tag_fast_path_detection_accepts_tag_lists():
    assert looks_like_danbooru_tags(
        "masterpiece, best quality, 1girl, solo, white dress, simple background"
    )


def test_prompt_pipeline_marks_missing_provider_as_llm_failure() -> None:
    class _Context:
        async def get_current_chat_provider_id(self, _umo):
            return ""

        def get_config(self, *, umo):
            return {"provider_settings": {}}

    class _Event:
        unified_msg_origin = "session"

    config = {"chiyo_preset_enabled": False}
    pipeline = PromptPipeline(
        context=_Context(),
        config=config,
        logger=_Logger(),
        danbooru_resolver=None,
        researcher=None,
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=_shorten,
    )

    result = asyncio.run(pipeline.build(_Event(), "画一个蓝色连衣裙女孩"))

    assert result.final_prompt == "画一个蓝色连衣裙女孩"
    assert result.summary["llm_failed"] is True
    assert result.summary["llm_error"] == "no_chat_provider"


def test_danbooru_tag_fast_path_detection_rejects_short_chinese_requests():
    assert not looks_like_danbooru_tags("画一个白裙子的女孩，简单背景")


def test_danbooru_tag_fast_path_accepts_one_chinese_character_name():
    assert looks_like_danbooru_tags(
        "1girl, solo, 狐莉, knee up, standing on one leg, foreshortening, "
        "pov, from below, holding sword, fighting stance, serious"
    )


def test_mixed_tag_fast_path_composes_fixed_character_without_llm():
    result = asyncio.run(
        _pipeline({"chiyo_preset": "aesthetic"}).build(
            object(),
            "1girl, solo, 狐莉, knee up, standing on one leg, foreshortening, "
            "pov, from below, holding sword, point a sword at audience, serious",
        )
    )

    assert result.summary["danbooru_fast_path"] is True
    assert result.summary["fixed_character_name"] == "狐莉"
    assert "point a sword at audience" in result.final_prompt
    assert "serious" in result.final_prompt
    assert "狐莉" not in result.final_prompt
    assert "smirk" not in result.final_prompt


def test_strategy_summary_keeps_debug_flags_compact():
    task = {
        "reference_image_requested": True,
        "reference_context_applied": False,
    }
    prompt_summary = {
        "raw_mode": True,
        "danbooru_fast_path": True,
        "llm_ok": False,
        "outfit_summary_ok": True,
        "web_search": False,
        "deep_thinking": False,
        "fixed_character": True,
        "fixed_character_name": "狐莉",
        "outfit_transfer": True,
        "llm_content_tag_count": 72,
        "final_prompt_chars": 360,
    }

    summary = build_strategy_summary(task, prompt_summary)

    assert summary["reference_requested"] is True
    assert summary["reference_applied"] is False
    assert summary["danbooru_fast_path"] is True
    assert summary["llm_ok"] is False
    assert summary["fixed_character_name"] == "狐莉"
    assert summary["content_tag_count"] == 72
    assert summary["final_prompt_chars"] == 360


def test_apply_verification_summary_updates_task_and_strategy():
    task = {
        "ok": True,
        "outputs": ["old.png"],
        "strategy_summary": {"raw_mode": False},
    }
    verification_summary = {
        "enabled": True,
        "skipped": False,
        "final_passed": False,
        "final_score": 5,
        "retry_count": 1,
    }
    payload = {"ok": True, "outputs": ["new.png"], "error": ""}

    updated = apply_verification_summary(task, verification_summary, payload)

    assert updated["outputs"] == ["new.png"]
    assert updated["verification_summary"] == verification_summary
    assert updated["strategy_summary"]["raw_mode"] is False
    assert updated["strategy_summary"]["verification"] == {
        "enabled": True,
        "skipped": False,
        "passed": False,
        "score": 5,
        "retry_count": 1,
    }


def test_last_task_debug_lines_use_strategy_summary():
    lines = build_last_task_debug_lines(
        {
            "time": "2026-07-05T10:00:00",
            "action": "generate",
            "ok": True,
            "outputs": ["x.png"],
            "strategy_summary": {
                "reference_requested": False,
                "reference_applied": False,
                "raw_mode": True,
                "danbooru_fast_path": True,
                "outfit_transfer": False,
                "llm_ok": True,
                "outfit_summary_ok": True,
                "fixed_character_name": "狐莉",
                "web_search": False,
                "deep_thinking": False,
                "final_prompt_chars": 120,
                "verification": {"passed": True, "retry_count": 0},
            },
            "verification_summary": {"enabled": True},
            "prompt_summary": {
                "stage_events": [
                    {"stage": "provider", "status": "ok"},
                    {"stage": "prompt_llm", "status": "ok"},
                ]
            },
        }
    )

    text = "\n".join(lines)
    assert "上次任务摘要" in text
    assert "角色：狐莉" in text
    assert "tags快路径=True" in text
    assert "自检：enabled=True passed=True retry=0" in text
    assert "阶段事件：provider=ok，prompt_llm=ok" in text
