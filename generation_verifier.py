from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from . import anima_verify
    from .task_summary import apply_verification_summary
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    import anima_verify
    from task_summary import apply_verification_summary


@dataclass
class VerificationOutcome:
    """Final generation payload plus optional image verification verdict."""

    payload: dict[str, Any]
    verdict: anima_verify.Verdict | None = None


class GenerationVerifier:
    """Verify generated images and optionally retry with a correction hint."""

    def __init__(
        self,
        *,
        context: Any,
        task_recorder: Any,
        generate_payload: Callable[..., Any],
        logger: Any,
        get_bool: Callable[[str, bool], bool],
        get_int: Callable[[str, int], int],
        get_str: Callable[[str, str], str],
    ):
        """Store dependencies for post-generation image verification.

        Args:
            context: AstrBot plugin context used to call the vision provider.
            task_recorder: Recorder for `last_task.json`.
            generate_payload: Callable that can run another generation attempt.
            logger: Logger compatible with AstrBot logger methods.
            get_bool: Config boolean accessor.
            get_int: Config integer accessor.
            get_str: Config string accessor.
        """
        self.context = context
        self._task_recorder = task_recorder
        self._generate_payload = generate_payload
        self.logger = logger
        self._bool = get_bool
        self._int = get_int
        self._str = get_str

    async def verify_and_maybe_retry(
        self,
        event: Any,
        payload: dict[str, Any],
        *,
        user_request: str,
        width: int | None,
        height: int | None,
        steps: int | None,
        cfg: float | None,
        negative_prompt: str | None,
    ) -> VerificationOutcome:
        """Verify the generated image; retry with a fix hint if needed.

        Verification is best-effort. Provider failures, unsupported image input,
        and unparseable model replies are recorded as skipped and must never
        block delivery of an otherwise valid image.

        Returns:
            Final payload to send and the last verification verdict, if any.
        """
        outcome = VerificationOutcome(payload=payload)
        if not self._bool("enable_verify", False):
            return outcome

        pass_score = self._int("verify_pass_score", 7)
        max_retry = max(0, self._int("max_verify_retry", 1))
        summary: dict[str, Any] = {
            "enabled": True,
            "pass_score": pass_score,
            "max_retry": max_retry,
            "retry_count": 0,
            "attempts": [],
        }
        initial_task = self._task_recorder.read(payload.get("task_id"))
        final_uses_initial_task = True

        if not payload.get("ok"):
            summary.update({"skipped": True, "skip_reason": "generation_failed"})
            self._record_summary(summary, payload, base_task=initial_task)
            return outcome

        outputs = self._output_paths(payload)
        if not outputs:
            summary.update({"skipped": True, "skip_reason": "no_output_image"})
            self._record_summary(summary, payload, base_task=initial_task)
            return outcome

        provider_id = await self._verify_provider_id(event)
        summary["provider_selected"] = bool(provider_id)
        if not provider_id:
            self.logger.info("[comfyui_agent] verify skipped: no provider available")
            summary.update({"skipped": True, "skip_reason": "no_provider"})
            self._record_summary(summary, payload, base_task=initial_task)
            return outcome

        llm_call = self._make_verify_llm_call(provider_id)
        verdict = await anima_verify.verify_image(
            llm_call,
            outputs[-1],
            user_request,
            pass_score=pass_score,
        )
        outcome.verdict = verdict
        summary["attempts"].append(self._verdict_summary(verdict))
        self.logger.info(
            "[comfyui_agent] verify: passed=%s score=%s skipped=%s",
            verdict.passed,
            verdict.score,
            verdict.skipped,
        )

        retries = 0
        while not verdict.passed and not verdict.skipped and retries < max_retry:
            retries += 1
            summary["retry_count"] = retries
            hint = verdict.fix_hint or (
                "；".join(verdict.issues) if verdict.issues else ""
            )
            self.logger.info(
                "[comfyui_agent] verify retry %s with hint: %s", retries, hint
            )
            retry_prompt = user_request
            if hint:
                retry_prompt = f"{user_request}\n【上次问题，请修正】{hint}"
            retry_payload = await self._generate_payload(
                event,
                retry_prompt,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                negative_prompt=negative_prompt,
            )
            if not retry_payload.get("ok"):
                summary["retry_failed"] = (
                    retry_payload.get("error") or "generation_failed"
                )
                break
            retry_outputs = self._output_paths(retry_payload)
            if not retry_outputs:
                summary["retry_failed"] = "no_output_image"
                break
            outcome.payload = retry_payload
            final_uses_initial_task = False
            verdict = await anima_verify.verify_image(
                llm_call,
                retry_outputs[-1],
                user_request,
                pass_score=pass_score,
            )
            outcome.verdict = verdict
            summary["attempts"].append(self._verdict_summary(verdict))
            self.logger.info(
                "[comfyui_agent] verify(after retry %s): passed=%s score=%s",
                retries,
                verdict.passed,
                verdict.score,
            )

        summary.update(
            {
                "skipped": bool(outcome.verdict.skipped) if outcome.verdict else False,
                "final_passed": bool(outcome.verdict.passed)
                if outcome.verdict
                else None,
                "final_score": int(outcome.verdict.score) if outcome.verdict else None,
                "issues": list(outcome.verdict.issues[:5]) if outcome.verdict else [],
                "error": outcome.verdict.error if outcome.verdict else "",
            }
        )
        self._record_summary(
            summary,
            outcome.payload,
            base_task=initial_task if final_uses_initial_task else None,
        )
        return outcome

    async def _verify_provider_id(self, event: Any) -> str:
        configured = self._str("verify_provider_id", "").strip()
        if configured:
            return configured
        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            provider_settings = cfg.get("provider_settings", {})
            return str(
                provider_settings.get("default_image_caption_provider_id")
                or provider_settings.get("default_provider_id")
                or ""
            ).strip()
        except Exception:  # noqa: BLE001 - config lookup is best-effort.
            return ""

    def _make_verify_llm_call(self, provider_id: str):
        async def llm_call(prompt: str, image_urls=None) -> str:
            if not provider_id:
                raise RuntimeError("no_verify_provider_available")
            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=anima_verify.ANIMA_VERIFY_SYSTEM,
                image_urls=image_urls or None,
                max_tokens=self._int("prompt_builder_max_tokens", 700),
            )
            return str(getattr(resp, "completion_text", "") or "")

        return llm_call

    @staticmethod
    def _output_paths(payload: dict[str, Any]) -> list[str]:
        return [str(p) for p in (payload.get("outputs") or []) if str(p).strip()]

    @staticmethod
    def _verdict_summary(verdict: anima_verify.Verdict) -> dict[str, Any]:
        return {
            "passed": bool(verdict.passed),
            "score": int(verdict.score),
            "skipped": bool(verdict.skipped),
            "issues": list(verdict.issues[:5]),
            "fix_hint": verdict.fix_hint,
            "error": verdict.error,
        }

    def _record_summary(
        self,
        summary: dict[str, Any],
        payload: dict[str, Any],
        *,
        base_task: dict[str, Any] | None = None,
    ) -> None:
        task = dict(base_task or self._task_recorder.read(payload.get("task_id")) or {})
        if not task:
            return
        self._task_recorder.write(apply_verification_summary(task, summary, payload))
