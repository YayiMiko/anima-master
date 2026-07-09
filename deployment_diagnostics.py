from __future__ import annotations

from typing import Any

try:
    from .image_input_diagnostics import image_input_diagnostic_lines
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from image_input_diagnostics import image_input_diagnostic_lines


def _flag(value: Any) -> str:
    return "正常" if value else "异常"


def _enabled(value: Any) -> str:
    return "开启" if value else "关闭"


def _connection_text(payload: dict[str, Any]) -> str:
    mode = str(payload.get("comfyui_connection_mode") or "")
    if mode == "remote":
        return "远程连接"
    if mode == "same-machine":
        return "同机连接"
    return "未知"


def _short(text: Any, limit: int = 120) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _error_summary(text: Any) -> str:
    value = str(text or "").strip()
    lowered = value.lower()
    if "connecttimeout" in lowered or "connect timeout" in lowered:
        return "连接超时"
    if "readtimeout" in lowered or "read timed out" in lowered:
        return "响应超时"
    if "connection refused" in lowered or "actively refused" in lowered:
        return "端口拒绝连接"
    if "httperror" in lowered:
        return "HTTP 错误"
    return _short(value or "未知", 120)


def _section(title: str, items: list[str]) -> list[str]:
    return ["", f"{title}：", *items]


def _join_limited(lines: list[str], limit: int = 1800) -> str:
    text = "\n".join(lines)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 24)].rstrip() + "\n...已截断"


def compact_status_text(payload: dict[str, Any]) -> str:
    """Render a short chat-visible ComfyUI status response.

    Args:
        payload: Status payload returned by the ComfyUI helper.

    Returns:
        Short human-readable status text.
    """
    if not payload.get("ok"):
        lines = [f"ComfyUI 状态检查失败：{payload.get('connection_issue') or _error_summary(payload.get('error'))}"]
        if payload.get("connection_hint"):
            lines.append(f"建议：{_short(payload.get('connection_hint'), 180)}")
        return "\n".join(lines)
    model_status = (
        f"UNET {_flag(payload.get('unet_available'))} / "
        f"CLIP {_flag(payload.get('clip_available'))} / "
        f"VAE {_flag(payload.get('vae_available'))}"
    )
    return "\n".join(
        [
            "ComfyUI 助手状态：",
            f"- 连接：{_connection_text(payload)}",
            f"- 地址：{payload.get('base_url')}",
            f"- GPU：{payload.get('gpu')}",
            f"- 显存：{payload.get('vram_free_mb')} / {payload.get('vram_total_mb')} MB",
            f"- 模型：{model_status}",
        ]
    )


def diagnostic_text(
    payload: dict[str, Any],
    config: dict[str, Any],
    last_task: dict[str, Any],
    image_input_summary: dict[str, Any] | None = None,
) -> str:
    """Render a deployment-focused diagnostic response.

    Args:
        payload: Status payload returned by the ComfyUI helper.
        config: Current plugin configuration without secrets.
        last_task: Last non-secret generation task summary.
        image_input_summary: Latest in-memory image input summary.

    Returns:
        Human-readable diagnostic text for server/local split deployments.
    """
    dns_checks = payload.get("dns_checks") if isinstance(payload.get("dns_checks"), dict) else {}
    dns_text = " / ".join(
        f"{host}:{_flag(ok)}" for host, ok in dns_checks.items()
    ) or "未检查"
    auto_start = bool(config.get("auto_start", False))
    remote_warning = ""
    if payload.get("comfyui_connection_mode") == "remote" and auto_start:
        remote_warning = "（远程 ComfyUI 不建议开启）"
    lines = ["Anima 诊断："]
    lines.extend(
        _section(
            "部署",
            [
                f"- AstrBot：{payload.get('runtime_platform') or '未知'} / {_connection_text(payload)}",
                f"- ComfyUI API：{_flag(payload.get('comfyui_api_reachable'))}",
                f"- 地址：{payload.get('base_url') or '未配置'}",
                f"- DNS：{dns_text}",
                f"- AstrBot 启动 ComfyUI：{_enabled(auto_start)}{remote_warning}",
            ],
        )
    )
    if payload.get("ok"):
        lines.extend(
            _section(
                "ComfyUI",
                [
                f"- ComfyUI：{payload.get('comfyui_version') or '未知'}",
                f"- GPU：{_short(payload.get('gpu') or '未知', 90)}",
                f"- 显存：{payload.get('vram_free_mb')} / {payload.get('vram_total_mb')} MB",
                f"- 模型：UNET {_flag(payload.get('unet_available'))} / CLIP {_flag(payload.get('clip_available'))} / VAE {_flag(payload.get('vae_available'))}",
                f"- 附加组件：图生图 {_flag(payload.get('img2img_available'))} / 放大 {_flag(payload.get('upscale_available'))} / 去背景 {_flag(payload.get('remove_bg_available'))}",
                ],
            )
        )
    else:
        items = [
            f"- 连接问题：{payload.get('connection_issue') or '未知'}",
            f"- 错误摘要：{_error_summary(payload.get('error'))}",
        ]
        if payload.get("connection_hint"):
            items.append(f"- 建议：{_short(payload.get('connection_hint'), 180)}")
        lines.extend(_section("ComfyUI", items))

    if last_task:
        prompt_summary = last_task.get("prompt_summary")
        if not isinstance(prompt_summary, dict):
            prompt_summary = {}
        delivery = last_task.get("delivery")
        if not isinstance(delivery, dict):
            delivery = {}
        items = [
                f"- 时间：{last_task.get('time') or '未知'}",
                f"- 动作：{last_task.get('action') or '未知'} / 成功：{last_task.get('ok')}",
                f"- 错误：{_error_summary(last_task.get('error') or '无')}",
                f"- 引用图：requested={last_task.get('reference_image_requested')} applied={last_task.get('reference_context_applied')}",
                f"- Prompt：失败={prompt_summary.get('llm_failed', False)} / 长度={prompt_summary.get('final_prompt_chars') or 0}",
                f"- 输出/发送：{len(last_task.get('outputs') or [])} 张 / {delivery.get('status') or '未记录'}",
                f"- ACK/失败：{delivery.get('ack_timeout', False)} / {delivery.get('send_failed', False)}",
        ]
        if delivery.get("error"):
            items.append(f"- 发送错误：{_error_summary(delivery.get('error'))}")
        lines.extend(_section("最近任务", items[:7]))
    else:
        lines.extend(_section("最近任务", ["- 暂无记录"]))
    lines.extend(image_input_diagnostic_lines(image_input_summary or {}, last_task))
    return _join_limited(lines)
