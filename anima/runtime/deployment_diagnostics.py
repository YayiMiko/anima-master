from __future__ import annotations

from typing import Any

try:
    from ..images.image_input_diagnostics import image_input_diagnostic_lines
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from anima.images.image_input_diagnostics import image_input_diagnostic_lines


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


def safe_error_summary(text: Any) -> str:
    """Classify an error without echoing its potentially private details."""
    value = str(text or "").strip()
    lowered = value.lower()
    if not value or lowered == "无":
        return "无"
    if "connecttimeout" in lowered or "connect timeout" in lowered:
        return "连接超时"
    if "readtimeout" in lowered or "read timed out" in lowered:
        return "响应超时"
    if "connection refused" in lowered or "actively refused" in lowered:
        return "端口拒绝连接"
    if "httperror" in lowered:
        return "HTTP 错误"
    if "connection" in lowered or "dns" in lowered or "name resolution" in lowered:
        return "连接失败"
    return "未分类错误（详情请查看服务器日志）"


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
        lines = [
            f"ComfyUI 状态检查失败：{safe_error_summary(payload.get('error') or payload.get('connection_issue'))}"
        ]
        lines.append("建议：确认 ComfyUI 已启动，并检查插件配置和网络连接。")
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
    dns_checks = (
        payload.get("dns_checks") if isinstance(payload.get("dns_checks"), dict) else {}
    )
    dns_text = (
        f"{sum(bool(ok) for ok in dns_checks.values())}/{len(dns_checks)} 项正常"
        if dns_checks
        else "未检查"
    )
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
                    f"- 显存：{payload.get('vram_free_mb')} / {payload.get('vram_total_mb')} MB",
                    f"- 模型：UNET {_flag(payload.get('unet_available'))} / CLIP {_flag(payload.get('clip_available'))} / VAE {_flag(payload.get('vae_available'))}",
                    f"- 附加组件：图生图 {_flag(payload.get('img2img_available'))} / 放大 {_flag(payload.get('upscale_available'))} / 去背景 {_flag(payload.get('remove_bg_available'))}",
                ],
            )
        )
    else:
        items = [
            f"- 错误摘要：{safe_error_summary(payload.get('error') or payload.get('connection_issue'))}",
        ]
        items.append("- 建议：确认 ComfyUI 已启动，并检查插件配置和网络连接。")
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
            f"- 错误：{safe_error_summary(last_task.get('error'))}",
            f"- 引用图：requested={last_task.get('reference_image_requested')} applied={last_task.get('reference_context_applied')}",
            f"- Prompt：失败={prompt_summary.get('llm_failed', False)} / 长度={prompt_summary.get('final_prompt_chars') or 0}",
            f"- 输出/发送：{len(last_task.get('outputs') or [])} 张 / {delivery.get('status') or '未记录'}",
            f"- ACK/失败：{delivery.get('ack_timeout', False)} / {delivery.get('send_failed', False)}",
        ]
        if delivery.get("error"):
            items.append(f"- 发送错误：{safe_error_summary(delivery.get('error'))}")
        lines.extend(_section("最近任务", items[:7]))
    else:
        lines.extend(_section("最近任务", ["- 暂无记录"]))
    lines.extend(image_input_diagnostic_lines(image_input_summary or {}, last_task))
    return _join_limited(lines)
