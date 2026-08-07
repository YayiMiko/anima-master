from __future__ import annotations

from typing import Any


def _error_text(exc: Exception) -> str:
    return str(getattr(exc, "wording", "") or getattr(exc, "message", "") or exc)


def is_ack_timeout(exc: Exception, action_failed_cls: Any) -> bool:
    """Return whether a platform send exception is an ACK timeout.

    Args:
        exc: Exception raised by the platform send API.
        action_failed_cls: Optional aiocqhttp ActionFailed class.

    Returns:
        True when the image may have been sent but the platform ACK timed out.
    """
    is_action_failed = action_failed_cls is not None and isinstance(
        exc, action_failed_cls
    )
    retcode = getattr(exc, "retcode", None)
    wording = _error_text(exc)
    return bool(is_action_failed and (retcode == 1200 or "Timeout" in wording))


def operation_failed_delivery(payload: dict[str, Any], message: str) -> dict[str, Any]:
    """Build delivery state for a failed ComfyUI operation."""
    return {
        "status": "operation_failed",
        "generated": False,
        "sent": False,
        "ack_timeout": False,
        "send_failed": False,
        "outputs": [],
        "error": str(payload.get("error") or ""),
        "message": message,
    }


def no_output_delivery(message: str) -> dict[str, Any]:
    """Build delivery state for a successful operation with no output files."""
    return {
        "status": "no_output",
        "generated": True,
        "sent": False,
        "ack_timeout": False,
        "send_failed": False,
        "outputs": [],
        "error": "no_sendable_output",
        "message": message,
    }


def sent_delivery(outputs: list[str], message: str) -> dict[str, Any]:
    """Build delivery state for confirmed image sends."""
    return {
        "status": "sent",
        "generated": True,
        "sent": True,
        "ack_timeout": False,
        "send_failed": False,
        "outputs": outputs,
        "error": "",
        "message": message,
    }


def skipped_delivery(outputs: list[str], message: str) -> dict[str, Any]:
    """Build delivery state when chat sending is disabled."""
    return {
        "status": "send_disabled",
        "generated": True,
        "sent": False,
        "ack_timeout": False,
        "send_failed": False,
        "outputs": outputs,
        "error": "",
        "message": message,
    }


def ack_timeout_delivery(
    outputs: list[str], output: str, exc: Exception, message: str
) -> dict[str, Any]:
    """Build an uncertain delivery state for platform ACK timeout."""
    return {
        "status": "delivery_uncertain",
        "generated": True,
        "sent": None,
        "ack_timeout": True,
        "send_failed": False,
        "notice_suppressed": True,
        "outputs": outputs,
        "last_output": output,
        "error": _error_text(exc)[:500],
        "message": message,
    }


def send_failed_delivery(
    outputs: list[str], output: str, exc: Exception, message: str
) -> dict[str, Any]:
    """Build delivery state for platform send failure."""
    return {
        "status": "send_failed",
        "generated": True,
        "sent": False,
        "ack_timeout": False,
        "send_failed": True,
        "outputs": outputs,
        "last_output": output,
        "error": _error_text(exc)[:500],
        "message": message,
    }
