from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


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

    async def generate_payload(
        self,
        event: Any,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        negative_prompt: str | None = None,
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

        Returns:
            Payload returned by the ComfyUI helper, or an early failure payload.
        """
        started_at = datetime.now()
        original_prompt = str(prompt or "").strip()
        reference_requested = self._wants_reference_image(original_prompt)
        task: dict[str, Any] = {
            "time": started_at.isoformat(timespec="seconds"),
            "action": "generate",
            "platform_id": event.get_platform_id(),
            "session_id": event.get_session_id(),
            "sender_id": event.get_sender_id(),
            "original_prompt": self._shorten(original_prompt, 1000),
            "reference_image_requested": reference_requested,
            "reference_context_applied": False,
            "width": width or self._int("width", 1024),
            "height": height or self._int("height", 1536),
            "steps": steps or self._int("steps", 30),
            "cfg": cfg or self._float("cfg", 5.0),
            "workflow": self._str("workflow", "anima_t2i"),
        }
        if not self._is_allowed(event):
            payload = {"ok": False, "error": "not_permitted"}
            task.update({"ok": False, "error": payload["error"]})
            self._task_recorder.write(task)
            return payload
        ready = await self._ensure_ready(event)
        if not ready.get("ok"):
            task.update({"ok": False, "error": ready.get("error") or "comfyui_not_ready"})
            self._task_recorder.write(task)
            return ready
        prompt = original_prompt
        if not prompt:
            payload = {"ok": False, "error": "missing_prompt"}
            task.update({"ok": False, "error": payload["error"]})
            self._task_recorder.write(task)
            return payload
        prompt = await self._augment_reference_image(event, prompt)
        if prompt is None:
            image_input_summary = dict(self._image_inputs.last_summary)
            payload = {
                "ok": False,
                "error": "reference_image_not_found",
                "image_input_summary": image_input_summary,
            }
            task.update(
                {
                    "ok": False,
                    "error": payload["error"],
                    "reference_image_found": False,
                    "image_input_summary": image_input_summary,
                }
            )
            self._task_recorder.write(task)
            return payload
        if reference_requested:
            task["image_input_summary"] = dict(self._image_inputs.last_summary)
            task["reference_context_summary"] = dict(self._reference_context.last_summary)
        task["reference_context_applied"] = reference_requested and prompt != original_prompt
        prompt = self._augment_quoted_spell(event, prompt)
        prompt = await self._build_prompt(event, prompt)
        task["prompt_summary"] = dict(self._prompt_summary())
        args = ["generate", "--prompt", prompt]
        if width:
            args.extend(["--width", str(int(width))])
        if height:
            args.extend(["--height", str(int(height))])
        if steps:
            args.extend(["--steps", str(int(steps))])
        if cfg:
            args.extend(["--cfg", str(float(cfg))])
        if negative_prompt:
            args.extend(["--negative-prompt", str(negative_prompt)])
        payload = await self._run_tool(args)
        task.update(
            {
                "ok": bool(payload.get("ok")),
                "error": payload.get("error") or "",
                "outputs": payload.get("outputs") or [],
                "elapsed_seconds": round((datetime.now() - started_at).total_seconds(), 2),
            }
        )
        if self._bool("debug_send_payload_enabled", False):
            task["tool_payload"] = payload
        self._task_recorder.write(task)
        return payload
