from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_strategy_summary(
    task: dict[str, Any],
    prompt_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact, non-secret strategy summary for `last_task.json`.

    Args:
        task: Current task summary fields.
        prompt_summary: Detailed prompt pipeline summary.

    Returns:
        A compact dict suitable for quick debugging and chat-side status.
    """
    task = _as_dict(task)
    prompt_summary = _as_dict(prompt_summary)
    return {
        "reference_requested": bool(task.get("reference_image_requested")),
        "reference_applied": bool(task.get("reference_context_applied")),
        "raw_mode": bool(prompt_summary.get("raw_mode")),
        "skipped_reason": prompt_summary.get("skipped_reason") or "",
        "llm_ok": prompt_summary.get(
            "llm_ok",
            not bool(prompt_summary.get("llm_failed")),
        ),
        "outfit_summary_ok": prompt_summary.get("outfit_summary_ok", True),
        "web_search": bool(prompt_summary.get("web_search")),
        "deep_thinking": bool(prompt_summary.get("deep_thinking")),
        "fixed_character": bool(prompt_summary.get("fixed_character")),
        "fixed_character_name": prompt_summary.get("fixed_character_name") or "",
        "default_style": bool(prompt_summary.get("default_style")),
        "sensual_mode": bool(prompt_summary.get("sensual_mode")),
        "asset_reference_mode": bool(prompt_summary.get("asset_reference_mode")),
        "outfit_transfer": bool(prompt_summary.get("outfit_transfer")),
        "outfit_transfer_source": prompt_summary.get("outfit_transfer_source") or "",
        "outfit_transfer_target": prompt_summary.get("outfit_transfer_target") or "",
        "content_tag_count": prompt_summary.get("llm_content_tag_count") or 0,
        "final_prompt_chars": prompt_summary.get("final_prompt_chars") or 0,
    }


def build_verification_brief(verification_summary: dict[str, Any]) -> dict[str, Any]:
    """Build the compact verification section inside `strategy_summary`."""
    verification_summary = _as_dict(verification_summary)
    return {
        "enabled": bool(verification_summary.get("enabled")),
        "skipped": bool(verification_summary.get("skipped")),
        "passed": verification_summary.get("final_passed"),
        "score": verification_summary.get("final_score"),
        "retry_count": verification_summary.get("retry_count", 0),
    }


def apply_verification_summary(
    task: dict[str, Any],
    verification_summary: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Return a task record updated with final verification and payload data."""
    task = dict(_as_dict(task))
    verification_summary = dict(_as_dict(verification_summary))
    payload = _as_dict(payload)
    task["verification_summary"] = verification_summary
    task["ok"] = bool(payload.get("ok"))
    task["error"] = payload.get("error") or ""
    outputs = payload.get("outputs") or []
    if outputs:
        task["outputs"] = outputs
    strategy = dict(_as_dict(task.get("strategy_summary")))
    strategy["verification"] = build_verification_brief(verification_summary)
    task["strategy_summary"] = strategy
    return task


def build_last_task_debug_lines(last_task: dict[str, Any]) -> list[str]:
    """Render the user-facing latest-task block for `/anm 调试状态`."""
    last_task = _as_dict(last_task)
    if not last_task:
        return []
    prompt_summary = _as_dict(last_task.get("prompt_summary"))
    strategy_summary = _as_dict(last_task.get("strategy_summary"))
    verification_summary = _as_dict(last_task.get("verification_summary"))
    verification_brief = _as_dict(strategy_summary.get("verification"))
    fixed_character_name = (
        strategy_summary.get("fixed_character_name")
        or prompt_summary.get("fixed_character_name")
        or "无"
    )
    final_prompt_chars = (
        strategy_summary.get("final_prompt_chars")
        or prompt_summary.get("final_prompt_chars")
        or 0
    )
    stage_events = prompt_summary.get("stage_events")
    if not isinstance(stage_events, list):
        stage_events = []
    event_text = _format_stage_events(stage_events[-6:])
    return [
        "",
        "上次任务摘要：",
        f"- 时间：{last_task.get('time') or '未知'}",
        f"- 动作：{last_task.get('action') or '未知'} / 成功：{last_task.get('ok')}",
        f"- 错误：{last_task.get('error') or '无'}",
        (
            "- 引用图："
            f"requested={strategy_summary.get('reference_requested', last_task.get('reference_image_requested'))} "
            f"applied={strategy_summary.get('reference_applied', last_task.get('reference_context_applied'))}"
        ),
        f"- 角色：{fixed_character_name}",
        (
            "- 搜索/思考："
            f"{strategy_summary.get('web_search', prompt_summary.get('web_search'))} / "
            f"{strategy_summary.get('deep_thinking', prompt_summary.get('deep_thinking'))}"
        ),
        (
            "- 策略："
            f"raw={strategy_summary.get('raw_mode')} "
            f"服装迁移={strategy_summary.get('outfit_transfer')}"
        ),
        (
            "- 提示词健康："
            f"llm={strategy_summary.get('llm_ok', True)} "
            f"outfit={strategy_summary.get('outfit_summary_ok', True)}"
        ),
        (
            "- 自检："
            f"enabled={verification_summary.get('enabled', False)} "
            f"passed={verification_brief.get('passed')} "
            f"retry={verification_brief.get('retry_count', 0)}"
        ),
        f"- 阶段事件：{event_text or '无'}",
        f"- 最终 prompt 长度：{final_prompt_chars}",
        f"- 输出：{len(last_task.get('outputs') or [])} 张",
    ]


def _format_stage_events(events: list[Any]) -> str:
    parts: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        stage = str(event.get("stage") or "").strip()
        status = str(event.get("status") or "").strip()
        reason = str(event.get("reason") or "").strip()
        if not stage or not status:
            continue
        item = f"{stage}={status}"
        if reason:
            item += f":{reason}"
        parts.append(item)
    return "，".join(parts)
