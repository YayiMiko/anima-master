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
    """Verify generated images and optionally retry with correction guidance."""

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

        Verification is best-effort for ordinary generation. Multi-person
        verification ranks every generated candidate and records structural
        failures, but still returns the best available image when no candidate
        fully satisfies the verifier.

        Returns:
            Final payload to send and the last verification verdict, if any.
        """
        outcome = VerificationOutcome(payload=payload)
        configured_verify = self._bool("enable_verify", False)
        if multi_person and not self._bool("multi_verify_enabled", True):
            return outcome
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

        pass_score = self._int(
            "multi_verify_pass_score" if multi_person else "verify_pass_score",
            6 if multi_person else 7,
        )
        max_retry = max(0, self._int("max_verify_retry", 1))
        if multi_person:
            candidate_count = min(3, max(1, self._int("multi_candidate_count", 2)))
            max_retry = candidate_count - 1
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

        provider_id = await self._verify_provider_id(event, multi_person=multi_person)
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
            item_tags = [
                str(tag).strip()
                for tag in (item.get("identity_tags") or [])
                if str(tag).strip()
            ]
            if item_canonical or item_tags:
                item_alias = str(
                    item.get("role") or item.get("alias") or "character"
                ).strip()
                item_name = str(item.get("name") or "").strip()
                identity_parts.append(
                    f"{item_alias} ({item_name}): "
                    f"{', '.join(([item_canonical] if item_canonical else []) + item_tags)}"
                )
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
            require_facts=multi_person,
        )
        payload = {**payload, "selected_output_path": outputs[-1]}
        outcome.payload = payload
        candidates: list[tuple[dict[str, Any], anima_verify.Verdict]] = [
            (payload, verdict)
        ]
        outcome.verdict = verdict
        attempt_summary = self._verdict_summary(verdict)
        attempt_summary["task_id"] = payload.get("task_id")
        summary["attempts"].append(attempt_summary)
        self.logger.info(
            "[comfyui_agent] verify: passed=%s score=%s skipped=%s",
            verdict.passed,
            verdict.score,
            verdict.skipped,
        )

        retries = 0
        prepared_prompt = str(payload.get("_prepared_prompt") or "").strip()
        prepared_prompt_summary = payload.get("_prepared_prompt_summary")
        if not isinstance(prepared_prompt_summary, dict):
            prepared_prompt_summary = prompt_summary
        expected_count = int(prompt_summary.get("planned_character_count") or 2)
        while (
            not verdict.skipped
            and (
                not verdict.passed
                or (
                    multi_person
                    and not self._multi_candidate_rank(verdict, expected_count)[0]
                )
            )
            and retries < max_retry
        ):
            retries += 1
            summary["retry_count"] = retries
            hint = verdict.fix_hint or (
                "；".join(verdict.issues) if verdict.issues else ""
            )
            self.logger.info(
                "[comfyui_agent] verify retry %s with hint: %s", retries, hint
            )
            retry_prompt = user_request
            retry_kwargs: dict[str, Any] = {}
            if multi_person and prepared_prompt:
                retry_kwargs = {
                    "prepared_prompt": prepared_prompt,
                    "prepared_prompt_summary": prepared_prompt_summary,
                }
            elif hint:
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
                **retry_kwargs,
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
            verdict = await anima_verify.verify_image(
                llm_call,
                retry_outputs[-1],
                user_request,
                pass_score=pass_score,
                require_facts=multi_person,
            )
            retry_payload = {
                **retry_payload,
                "selected_output_path": retry_outputs[-1],
            }
            candidates.append((retry_payload, verdict))
            outcome.payload = retry_payload
            final_uses_initial_task = False
            outcome.verdict = verdict
            attempt_summary = self._verdict_summary(verdict)
            attempt_summary["task_id"] = retry_payload.get("task_id")
            summary["attempts"].append(attempt_summary)
            self.logger.info(
                "[comfyui_agent] verify(after retry %s): passed=%s score=%s",
                retries,
                verdict.passed,
                verdict.score,
            )

        multi_accepted = True
        if multi_person:
            ranked = [
                (
                    self._multi_candidate_rank(candidate_verdict, expected_count),
                    index,
                    candidate_payload,
                    candidate_verdict,
                )
                for index, (candidate_payload, candidate_verdict) in enumerate(
                    candidates
                )
            ]
            eligible = [item for item in ranked if item[0][0]]
            selected = max(eligible or ranked, key=lambda item: item[0][1])
            multi_accepted = bool(eligible)
            _, selected_index, selected_payload, selected_verdict = selected
            outcome.payload = selected_payload
            outcome.verdict = selected_verdict
            final_uses_initial_task = selected_index == 0
            summary.update(
                {
                    "candidate_count": len(candidates),
                    "eligible_candidate_count": len(eligible),
                    "selected_attempt": selected_index + 1,
                    "selection_policy": (
                        "best_structurally_valid_candidate"
                        if eligible
                        else "best_available_candidate"
                    ),
                    "degraded_delivery": not multi_accepted,
                }
            )

        summary.update(
            {
                "skipped": bool(outcome.verdict.skipped) if outcome.verdict else False,
                "final_passed": (
                    multi_accepted
                    if multi_person
                    else bool(outcome.verdict.passed)
                    if outcome.verdict
                    else None
                ),
                "final_score": int(outcome.verdict.score) if outcome.verdict else None,
                "issues": list(outcome.verdict.issues[:5]) if outcome.verdict else [],
                "error": outcome.verdict.error if outcome.verdict else "",
            }
        )
        if multi_person and not multi_accepted:
            if self._bool("multi_send_degraded_candidate", True):
                outcome.payload = {
                    **outcome.payload,
                    "verification_warning": "multi_person_verification_failed",
                }
            else:
                outcome.payload = {
                    **outcome.payload,
                    "ok": False,
                    "error": "multi_person_verification_failed",
                }
        self._record_summary(
            summary,
            outcome.payload,
            base_task=initial_task if final_uses_initial_task else None,
        )
        return outcome

    async def _verify_provider_id(self, event: Any, *, multi_person: bool) -> str:
        configured = (
            self._str("multi_verify_provider_id", "").strip() if multi_person else ""
        )
        if not configured:
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
            system_prompt += (
                "JSON 中还必须增加 multi_facts 对象，只报告直接观察到的事实："
                '"visible_person_count" 为可见人物整数；'
                '"layout" 只能是 single_scene、split_screen、collage、'
                'multiple_views 或 unknown；"identity_match" 只能是 correct、'
                'partial、swapped、wrong 或 unknown；"interaction_direction" '
                "只能是 correct、reversed、unclear、wrong 或 unknown。"
                '另给出 0.0 到 1.0 的 "identity_confidence" 和 '
                '"direction_confidence"，以及布尔值 "major_anatomy_issue"；'
                "只有能清楚看见证据时才给高置信度。"
                "不要让总分替代这些客观字段。"
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
            "checks": dict(verdict.checks),
            "visible_person_count": verdict.visible_person_count,
            "layout": verdict.layout,
            "identity_match": verdict.identity_match,
            "identity_confidence": verdict.identity_confidence,
            "interaction_direction": verdict.interaction_direction,
            "direction_confidence": verdict.direction_confidence,
            "major_anatomy_issue": verdict.major_anatomy_issue,
            "error": verdict.error,
        }

    @staticmethod
    def _multi_candidate_rank(
        verdict: anima_verify.Verdict,
        expected_count: int,
    ) -> tuple[bool, int]:
        """Return eligibility and rank for one multi-person candidate.

        Args:
            verdict: Vision result containing observable multi-person facts.
            expected_count: Number of people planned for the request.

        Returns:
            A pair of whether the candidate is deliverable and its rank score.
        """
        hard_failure = (
            (
                verdict.visible_person_count is not None
                and verdict.visible_person_count != expected_count
            )
            or verdict.layout in {"split_screen", "collage", "multiple_views"}
            or verdict.major_anatomy_issue
            or (
                verdict.identity_match in {"swapped", "wrong"}
                and verdict.identity_confidence >= 0.7
            )
            or (
                verdict.interaction_direction in {"reversed", "wrong"}
                and verdict.direction_confidence >= 0.7
            )
        )
        eligible = bool(verdict.skipped or (not hard_failure and verdict.score >= 5))
        rank = int(verdict.score)
        if verdict.visible_person_count == expected_count:
            rank += 100
        if verdict.layout == "single_scene":
            rank += 50
        if verdict.major_anatomy_issue:
            rank -= 40
        if verdict.interaction_direction == "correct":
            rank += 8
        elif verdict.interaction_direction == "unclear":
            rank += 2
        if verdict.identity_match == "correct":
            rank += 5
        elif verdict.identity_match == "partial":
            rank += 1
        return eligible, rank

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
