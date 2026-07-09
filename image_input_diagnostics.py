from __future__ import annotations

from typing import Any


def _value(summary: dict[str, Any], key: str, default: str = "无") -> str:
    value = summary.get(key)
    if value is None or value == "":
        return default
    return str(value)


def _short_path(value: str, limit: int = 96) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text or "无"
    normalized = text.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    tail = "/".join(parts[-4:]) if parts else normalized[-limit:]
    if len(tail) <= limit - 3:
        return ".../" + tail
    return "..." + tail[-(limit - 3) :]


def image_input_diagnostic_lines(
    current_summary: dict[str, Any],
    last_task: dict[str, Any],
) -> list[str]:
    """Build chat-visible image input diagnostic lines.

    Args:
        current_summary: In-memory summary from the latest image input attempt.
        last_task: Last non-secret generation task summary.

    Returns:
        Lines suitable for `/anm 诊断`.
    """
    summary = current_summary if current_summary else {}
    source_label = "最近图片输入"
    if not summary:
        task_summary = last_task.get("image_input_summary")
        if isinstance(task_summary, dict):
            summary = task_summary
            source_label = "最近任务图片输入"
    lines = ["", f"{source_label}："]
    if not summary:
        lines.append("- 暂无记录")
        return lines

    source = _value(summary, "source")
    path = _short_path(_value(summary, "path"))
    label = _value(summary, "label")
    lines.extend(
        [
            f"- 来源：{source}",
            f"- 标签：{label}",
            f"- 路径：{path}",
        ]
    )
    if "size" in summary:
        lines.append(f"- 大小：{summary.get('size')} bytes")
    if "original_name" in summary:
        lines.append(f"- 原始名：{_value(summary, 'original_name')}")
    count_parts = []
    for key, label_name in (
        ("direct_images", "直接图"),
        ("reply_images", "引用图"),
        ("raw_images", "原始段"),
    ):
        if key in summary:
            count_parts.append(f"{label_name}={summary.get(key)}")
    if count_parts:
        lines.append("- 检测数量：" + " / ".join(count_parts))
    return lines
