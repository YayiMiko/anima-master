from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any


class GenerationTaskRunner:
    """Orchestrate one text-to-image generation task."""

    def __init__(
        self,
        *,
        task_recorder: Any,
        image_inputs: Any,
        reference_context: Any,
        is_allowed: Callable[[Any], bool],
        ensure_ready: Callable[[Any], Any],
        wants_reference_image: Callable[[str], bool],
        augment_reference_image: Callable[[Any, str], Any],
        augment_quoted_spell: Callable[[Any, str], str],
        build_prompt: Callable[[Any, str], Any],
        prompt_summary: Callable[[], dict[str, Any]],
        run_tool: Callable[[list[str]], Any],
        get_bool: Callable[[str, bool], bool],
        get_int: Callable[[str, int], int],
        get_float: Callable[[str, float], float],
        get_str: Callable[[str, str], str],
        shorten: Callable[[str, int], str],
        maintenance: Callable[[], Any] | None = None,
    ):
        """Store dependencies required to run one generation.

        Args:
            task_recorder: Recorder that writes `last_task.json`.
            image_inputs: Image resolver with `last_summary`.
            reference_context: Reference-context builder with `last_summary`.
            is_allowed: Permission checker for the current event.
            ensure_ready: ComfyUI readiness checker.
            wants_reference_image: Predicate for reference-image requests.
            augment_reference_image: Reference-image prompt augmenter.
            augment_quoted_spell: Quoted spell prompt augmenter.
            build_prompt: Final prompt builder.
            prompt_summary: Callable returning the latest prompt summary.
            run_tool: Main ComfyUI helper runner.
            get_bool: Config boolean accessor.
            get_int: Config integer accessor.
            get_float: Config float accessor.
            get_str: Config string accessor.
            shorten: Text-shortening helper.
            maintenance: Optional periodic storage maintenance callback.
        """
        self._task_recorder = task_recorder
        self._image_inputs = image_inputs
        self._reference_context = reference_context
        self._is_allowed = is_allowed
        self._ensure_ready = ensure_ready
        self._wants_reference_image = wants_reference_image
        self._augment_reference_image = augment_reference_image
        self._augment_quoted_spell = augment_quoted_spell
        self._build_prompt = build_prompt
        self._prompt_summary = prompt_summary
        self._run_tool = run_tool
        self._bool = get_bool
        self._int = get_int
        self._float = get_float
        self._str = get_str
        self._shorten = shorten
        self._maintenance = maintenance

    async def generate_payload(
        self,
        event: Any,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        negative_prompt: str | None = None,
        multi_person: bool = False,
        prepared_prompt: str | None = None,
        prepared_prompt_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run one generation request and persist a task summary.

        Args:
            event: AstrBot message event.
            prompt: User prompt text.
            width: Optional width override.
            height: Optional height override.
            steps: Optional steps override.
            cfg: Optional CFG override.
            negative_prompt: Optional negative prompt override.
            multi_person: Whether to use structured multi-person prompt planning.
            prepared_prompt: Previously validated final prompt reused by a
                multi-person verification retry.
            prepared_prompt_summary: Summary paired with prepared_prompt.

        Returns:
            Payload returned by the ComfyUI helper, or an early failure payload.
        """
        started_at = datetime.now()
        original_prompt = str(prompt or "").strip()
        reference_requested = self._wants_reference_image(original_prompt)
        explicit_size = width is not None or height is not None
        requested_width = width if width is not None else self._int("width", 1024)
        requested_height = height if height is not None else self._int("height", 1536)
        task = self._task_recorder.build_generation_start(
            event=event,
            started_at=started_at,
            original_prompt=original_prompt,
            reference_requested=reference_requested,
            width=requested_width,
            height=requested_height,
            explicit_size=explicit_size,
            steps=steps or self._int("steps", 30),
            cfg=cfg or self._float("cfg", 5.0),
            workflow=self._str("workflow", "anima_t2i"),
            shorten=self._shorten,
        )
        if not self._is_allowed(event):
            payload = {
                "ok": False,
                "error": "not_permitted",
                "task_id": task["task_id"],
            }
            self._task_recorder.mark_failure(task, payload["error"])
            self._persist_task(task)
            return payload
        ready = await self._ensure_ready(event)
        if not ready.get("ok"):
            ready["task_id"] = task["task_id"]
            status = ready.get("status")
            if isinstance(status, dict):
                task["comfyui_status"] = {
                    key: status.get(key)
                    for key in (
                        "comfyui_api_reachable",
                        "capabilities_checked",
                        "unet_available",
                        "clip_available",
                        "vae_available",
                        "connection_issue",
                        "connection_hint",
                        "error",
                    )
                    if key in status
                }
            self._task_recorder.mark_failure(
                task, ready.get("error") or "comfyui_not_ready"
            )
            self._persist_task(task)
            return ready
        prompt = original_prompt
        if not prompt:
            payload = {
                "ok": False,
                "error": "missing_prompt",
                "task_id": task["task_id"],
            }
            self._task_recorder.mark_failure(task, payload["error"])
            self._persist_task(task)
            return payload
        if prepared_prompt is not None:
            prompt = str(prepared_prompt).strip()
            prompt_summary = dict(prepared_prompt_summary or {})
            prompt_summary["multi_person_prepared_retry"] = True
        else:
            prompt = await self._augment_reference_image(event, prompt)
            if prompt is None:
                image_input_summary = dict(self._image_inputs.last_summary)
                payload = {
                    "ok": False,
                    "error": "reference_image_not_found",
                    "task_id": task["task_id"],
                    "image_input_summary": image_input_summary,
                }
                self._task_recorder.mark_reference_missing(task, image_input_summary)
                self._persist_task(task)
                return payload
            if reference_requested:
                self._task_recorder.mark_reference_context(
                    task,
                    image_input_summary=dict(self._image_inputs.last_summary),
                    reference_context_summary=dict(
                        self._reference_context.last_summary
                    ),
                    applied=prompt != original_prompt,
                )
            prompt = self._augment_quoted_spell(event, prompt)
            prompt = await self._build_prompt(
                event,
                prompt,
                multi_person=multi_person,
                original_user_prompt=original_prompt,
            )
            prompt_summary = dict(self._prompt_summary())
        self._task_recorder.mark_prompt_built(task, prompt_summary)
        if multi_person and (
            not prompt or prompt_summary.get("multi_person_plan_failed")
        ):
            payload = {
                "ok": False,
                "error": "multi_person_plan_failed",
                "task_id": task["task_id"],
            }
            self._task_recorder.mark_failure(task, payload["error"])
            self._persist_task(task)
            return payload
        args = ["generate", "--prompt", prompt]
        if width:
            args.extend(["--width", str(int(width))])
        if height:
            args.extend(["--height", str(int(height))])
        if explicit_size:
            args.append("--override-size")
        if steps:
            args.extend(["--steps", str(int(steps))])
        if cfg:
            args.extend(["--cfg", str(float(cfg))])
        if negative_prompt:
            args.extend(["--negative-prompt", str(negative_prompt)])
        payload = await self._run_tool(args)
        payload["task_id"] = task["task_id"]
        if multi_person:
            payload["_prepared_prompt"] = prompt
            payload["_prepared_prompt_summary"] = prompt_summary
        if prompt_summary.get("llm_failed"):
            payload["prompt_degraded"] = True
            payload["prompt_degraded_reason"] = str(
                prompt_summary.get("llm_error") or "prompt_builder_failed"
            )
        character_status = str(prompt_summary.get("character_resolution_status") or "")
        unresolved_count = int(prompt_summary.get("unresolved_character_count") or 0)
        if (
            prompt_summary.get("named_character_detected")
            and character_status in {"unresolved", "source_unavailable"}
        ) or unresolved_count:
            payload["character_resolution_warning"] = True
            payload["character_resolution_status"] = (
                character_status or "partially_unresolved"
            )
            payload["unresolved_character_count"] = unresolved_count
        self._task_recorder.mark_completed(
            task,
            payload=payload,
            elapsed_seconds=round((datetime.now() - started_at).total_seconds(), 2),
            include_payload=self._bool("debug_send_payload_enabled", False),
        )
        self._persist_task(task)
        return payload

    def _persist_task(self, task: dict[str, Any]) -> None:
        """Persist a task and trigger bounded periodic maintenance.

        Args:
            task: Mutable non-secret task record.
        """
        self._task_recorder.write(task)
        maintenance = getattr(self, "_maintenance", None)
        if maintenance is not None:
            maintenance()

    def record_delivery(
        self,
        task_id: str | None,
        delivery: dict[str, Any] | None,
    ) -> None:
        """Persist delivery state into its originating task record.

        Args:
            task_id: Identifier returned by the originating generation request.
            delivery: Delivery state produced after sending generated outputs.
        """
        if not task_id or not isinstance(delivery, dict) or not delivery:
            return
        task = self._task_recorder.read(task_id)
        if not task:
            return
        self._task_recorder.mark_delivery(task, delivery)
        self._persist_task(task)
