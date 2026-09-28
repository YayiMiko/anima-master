from __future__ import annotations

from typing import Any


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

    lines.extend(
        [
            f"- 图片：{'已找到' if summary.get('path') else '未找到'}",
        ]
    )
    if "size" in summary:
        lines.append(f"- 大小：{summary.get('size')} bytes")
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
