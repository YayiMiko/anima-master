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
        multi_person: bool = False,
    ) -> VerificationOutcome:
        """Verify the generated image; retry with a fix hint if needed.

        Verification is best-effort. Provider failures, unsupported image input,
        and unparseable model replies are recorded as skipped and must never
        block delivery of an otherwise valid image.

        Returns:
            Final payload to send and the last verification verdict, if any.
        """
        outcome = VerificationOutcome(payload=payload)
        configured_verify = self._bool("enable_verify", False)
        initial_task = self._task_recorder.read(payload.get("task_id"))
        prompt_summary = initial_task.get("prompt_summary")
        if not isinstance(prompt_summary, dict):
            prompt = initial_task.get("prompt")
            prompt_summary = (
                prompt.get("summary")
                if isinstance(prompt, dict) and isinstance(prompt.get("summary"), dict)
                else {}
            )
        named_character = bool(prompt_summary.get("named_character_detected"))
        if not configured_verify and not multi_person and not named_character:
            return outcome

        pass_score = self._int("verify_pass_score", 7)
        max_retry = max(0, self._int("max_verify_retry", 1))
        summary: dict[str, Any] = {
            "enabled": True,
            "pass_score": pass_score,
            "max_retry": max_retry,
            "retry_count": 0,
            "attempts": [],
            "forced_multi_person": bool(multi_person and not configured_verify),
            "forced_named_character": bool(
                named_character and not configured_verify and not multi_person
            ),
        }
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

        identity_parts: list[str] = []
        canonical_tag = str(prompt_summary.get("character_canonical_tag") or "").strip()
        identity_tags = [
            str(tag).strip()
            for tag in (prompt_summary.get("character_identity_tags") or [])
            if str(tag).strip()
        ]
        if canonical_tag:
            identity_parts.append(
                f"{canonical_tag}: {', '.join(identity_tags[1:]) or 'no anchors'}"
            )
        for item in prompt_summary.get("character_resolution_statuses") or []:
            if not isinstance(item, dict):
                continue
            item_canonical = str(item.get("canonical_tag") or "").strip()
            if item_canonical:
                identity_parts.append(item_canonical)
        llm_call = self._make_verify_llm_call(
            provider_id,
            multi_person=multi_person,
            character_identity="; ".join(identity_parts[:4]),
        )
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
                multi_person=multi_person,
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

    def _make_verify_llm_call(
        self,
        provider_id: str,
        *,
        multi_person: bool = False,
        character_identity: str = "",
    ):
        system_prompt = anima_verify.ANIMA_VERIFY_SYSTEM
        if multi_person:
            system_prompt += (
                "\n这是 /anm 多人任务。还必须严格检查：实际人物数量是否符合请求；"
                "每个角色是否只出现一次；是否出现分屏、漫画格、多视图、克隆或额外人物；"
                "固定角色的发色、瞳色、种族和标志性配饰是否串到其他角色；"
                "互动的主动方、承受方和空间位置是否正确。"
            )
        if character_identity:
            system_prompt += (
                "\n这是已解析到现有作品角色的任务。请检查角色是否可辨认，重点核对"
                "标志性的发色、瞳色、发型、种族特征和固定配饰；不要因服装或场景"
                f"变化误判。预期角色及稳定外观锚点：{character_identity}。"
            )

        async def llm_call(prompt: str, image_urls=None) -> str:
            if not provider_id:
                raise RuntimeError("no_verify_provider_available")
            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=system_prompt,
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
