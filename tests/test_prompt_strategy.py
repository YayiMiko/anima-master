from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from prompt_pipeline import PromptPipeline
from prompt_presets import looks_like_danbooru_tags
from prompt_trace import PromptBuildTrace
from task_summary import (
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


def test_danbooru_tag_fast_path_detection_accepts_tag_lists():
    assert looks_like_danbooru_tags(
        "masterpiece, best quality, 1girl, solo, white dress, simple background"
    )


def test_danbooru_tag_fast_path_detection_rejects_short_chinese_requests():
    assert not looks_like_danbooru_tags("画一个白裙子的女孩，简单背景")


def test_prompt_trace_records_raw_fast_path():
    trace = PromptBuildTrace(
        mode="txt2img",
        original_prompt="1girl, solo",
        prompt_optimize_enabled=True,
        shorten=_shorten,
    )

    trace.mark_raw("danbooru_tags_detected", "1girl, solo", danbooru_fast_path=True)
    summary = trace.to_summary()

    assert summary["raw_mode"] is True
    assert summary["danbooru_fast_path"] is True
    assert summary["skipped_reason"] == "danbooru_tags_detected"
    assert summary["llm_ok"] is True
    assert summary["stage_events"] == [
        {
            "stage": "direct_path",
            "status": "danbooru_fast_path",
            "reason": "danbooru_tags_detected",
        }
    ]


def test_prompt_pipeline_direct_path_records_optimizer_disabled():
    trace = PromptBuildTrace(
        mode="txt2img",
        original_prompt="画一个女孩",
        prompt_optimize_enabled=False,
        shorten=_shorten,
    )
    direct = _pipeline({"prompt_optimize_enabled": False})._try_direct_prompt_path(
        "画一个女孩",
        trace,
    )

    assert direct == "画一个女孩"
    assert trace.to_summary()["skipped_reason"] == "prompt_optimize_disabled"
    assert trace.to_summary()["stage_events"][0]["status"] == "skipped"


def test_prompt_pipeline_direct_path_records_tag_fast_path():
    tags = "masterpiece, best quality, 1girl, solo, white dress, simple background"
    trace = PromptBuildTrace(
        mode="txt2img",
        original_prompt=tags,
        prompt_optimize_enabled=True,
        shorten=_shorten,
    )
    direct = _pipeline()._try_direct_prompt_path(tags, trace)

    assert direct == tags
    assert trace.to_summary()["danbooru_fast_path"] is True
    assert trace.to_summary()["stage_events"][0]["status"] == "danbooru_fast_path"


def test_prompt_trace_records_final_prompt_fields():
    class Built:
        raw_mode = False
        used_fixed_character = True
        character_name = "狐莉"
        used_sensual_mode = False
        used_default_style = True
        required_core_tags = ["huli"]
        content_tags = "1girl, solo"
        final_prompt = "masterpiece, 1girl, solo"

    class OutfitPlan:
        enabled = True
        source_subject = "source"
        target_character = "狐莉"

    trace = PromptBuildTrace(
        mode="txt2img",
        original_prompt="狐莉穿同款衣服",
        prompt_optimize_enabled=True,
        shorten=_shorten,
    )
    trace.mark_llm_failed()
    trace.mark_final(
        built=Built(),
        web_search=True,
        deep_thinking=True,
        search_reason="keyword",
        thinking_reason="keyword",
        outfit_plan=OutfitPlan(),
        outfit_summary_source="search_summary",
        outfit_summary="dress, ribbon",
        asset_reference_mode=True,
        content_tag_count=2,
        short_content_retry=False,
        prompt_builder_template_customized=False,
        final_prompt_head="masterpiece, 1girl, solo",
    )
    summary = trace.to_summary()

    assert summary["llm_ok"] is False
    assert summary["stage_events"][0]["stage"] == "prompt_llm"
    assert summary["web_search"] is True
    assert summary["fixed_character_name"] == "狐莉"
    assert summary["outfit_transfer"] is True
    assert summary["final_prompt_chars"] == len(Built.final_prompt)


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
