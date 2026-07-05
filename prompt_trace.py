from __future__ import annotations

from typing import Any, Callable


class PromptBuildTrace:
    """Collect non-secret prompt pipeline decisions in one place."""

    def __init__(
        self,
        *,
        mode: str,
        original_prompt: str,
        prompt_optimize_enabled: bool,
        shorten: Callable[[str, int], str],
    ):
        """Create a prompt trace for one build.

        Args:
            mode: Generation mode, such as `txt2img` or `img2img`.
            original_prompt: User prompt after message/reference augmentation.
            prompt_optimize_enabled: Whether the optimizer is enabled.
            shorten: Text-shortening helper for safe task summaries.
        """
        self._shorten = shorten
        self._summary: dict[str, Any] = {
            "prompt_optimize_enabled": prompt_optimize_enabled,
            "mode": mode,
            "original_prompt_head": shorten(original_prompt, 600),
            # Health flags are consumed by user-facing warnings and
            # `strategy_summary`; keep defaults explicit.
            "llm_ok": True,
            "outfit_summary_ok": True,
            "stage_events": [],
        }

    def add_event(self, stage: str, status: str, reason: str = "") -> None:
        """Append a compact stage event for debugging fallback paths."""
        events = self._summary.setdefault("stage_events", [])
        if not isinstance(events, list):
            events = []
            self._summary["stage_events"] = events
        event = {
            "stage": str(stage or "unknown")[:40],
            "status": str(status or "unknown")[:40],
        }
        reason = str(reason or "").strip()
        if reason:
            event["reason"] = self._shorten(reason, 120)
        events.append(event)
        if len(events) > 30:
            del events[:-30]

    def mark_skipped(
        self,
        reason: str,
        final_prompt: str,
        *,
        stage: str = "direct_path",
        status: str = "skipped",
    ) -> None:
        """Record a pipeline skip that still returns a usable prompt."""
        self.add_event(stage, status, reason)
        self._summary.update(
            {
                "skipped_reason": reason,
                "final_prompt_head": self._shorten(final_prompt, 600),
                "final_prompt_chars": len(final_prompt),
            }
        )

    def mark_raw(self, reason: str, final_prompt: str, *, danbooru_fast_path: bool = False) -> None:
        """Record a raw/direct-tags path."""
        status = "danbooru_fast_path" if danbooru_fast_path else "raw"
        self.add_event("direct_path", status, reason)
        self._summary.update(
            {
                "raw_mode": True,
                "danbooru_fast_path": bool(danbooru_fast_path),
                "skipped_reason": reason,
                "final_prompt_head": self._shorten(final_prompt, 600),
                "final_prompt_chars": len(final_prompt),
            }
        )

    def mark_outfit_summary_failed(self, reason: str = "") -> None:
        """Record failure of the optional outfit-summary LLM stage."""
        self.add_event("outfit_summary", "failed", reason)
        self._summary["outfit_summary_ok"] = False

    def mark_llm_failed(self, reason: str = "") -> None:
        """Record failure of the main prompt-builder LLM stage."""
        self.add_event("prompt_llm", "failed", reason)
        self._summary["llm_ok"] = False

    def mark_final(
        self,
        *,
        built: Any,
        web_search: bool,
        deep_thinking: bool,
        search_reason: str,
        thinking_reason: str,
        outfit_plan: Any,
        outfit_summary_source: str,
        outfit_summary: str,
        asset_reference_mode: bool,
        content_tag_count: int,
        short_content_retry: bool,
        prompt_builder_template_customized: bool,
        final_prompt_head: str,
    ) -> None:
        """Record the final prompt composition result."""
        self._summary.update(
            {
                "raw_mode": built.raw_mode,
                "web_search": bool(web_search),
                "deep_thinking": bool(deep_thinking),
                "search_reason": search_reason or "",
                "thinking_reason": thinking_reason or "",
                "fixed_character": built.used_fixed_character,
                "fixed_character_name": built.character_name,
                "sensual_mode": built.used_sensual_mode,
                "default_style": built.used_default_style,
                "required_core_tags": list(built.required_core_tags),
                "outfit_transfer": outfit_plan.enabled,
                "outfit_transfer_source": outfit_plan.source_subject,
                "outfit_transfer_target": outfit_plan.target_character,
                "outfit_summary_source": outfit_summary_source,
                "outfit_summary_chars": len(outfit_summary),
                "asset_reference_mode": bool(asset_reference_mode),
                "llm_content_tag_count": int(content_tag_count),
                "short_content_retry": bool(short_content_retry),
                "llm_content_chars": len(built.content_tags),
                "final_prompt_chars": len(built.final_prompt),
                "final_prompt_head": final_prompt_head,
                "prompt_builder_template_customized": bool(prompt_builder_template_customized),
            }
        )

    def add_debug_payload(
        self,
        *,
        llm_prompt: str,
        outfit_summary: str,
        llm_content: str,
        final_prompt: str,
    ) -> None:
        """Record verbose debug fields when the user explicitly enables them."""
        self._summary.update(
            {
                "llm_prompt": llm_prompt,
                "outfit_summary": outfit_summary,
                "llm_content": llm_content,
                "final_prompt": final_prompt,
            }
        )

    def to_summary(self) -> dict[str, Any]:
        """Return a serializable copy of the current trace."""
        return dict(self._summary)
