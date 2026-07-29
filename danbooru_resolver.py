from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from .danbooru_tags import (
        DEFAULT_DONMAI_BASE_URLS,
        DEFAULT_USER_AGENT,
        character_resolution_requested,
        required_core_tags_for_prompt,
        resolve_core_tags,
    )
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from danbooru_tags import (
        DEFAULT_DONMAI_BASE_URLS,
        DEFAULT_USER_AGENT,
        character_resolution_requested,
        required_core_tags_for_prompt,
        resolve_core_tags,
    )


@dataclass(frozen=True)
class DanbooruResolveOutcome:
    """Request-scoped character resolution result."""

    text: str
    status: str = "not_requested"
    canonical_tag: str = ""
    identity_tags: tuple[str, ...] = ()
    candidate_hints: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    explicit_request: bool = False


class DanbooruResolver:
    """Configuration-aware resolver for Danbooru character core tags."""

    def __init__(
        self,
        *,
        logger: Any,
        cache: dict[str, Any],
        get_bool: Callable[[str, bool], bool],
        get_int: Callable[[str, int], int],
        get_float: Callable[[str, float], float],
        get_str: Callable[[str, str], str],
    ):
        """Store Danbooru lookup dependencies.

        Args:
            logger: Logger compatible with AstrBot logger methods.
            cache: Shared timestamped Danbooru lookup cache.
            get_bool: Config boolean accessor.
            get_int: Config integer accessor.
            get_float: Config float accessor.
            get_str: Config string accessor.
        """
        self.logger = logger
        self._cache = cache
        self._bool = get_bool
        self._int = get_int
        self._float = get_float
        self._str = get_str

    def required_core_tags_for_prompt(self, user_prompt: str) -> tuple[str, ...]:
        """Return locally known character anchors explicitly requested by the user.

        Args:
            user_prompt: User prompt text.

        Returns:
            Required core tags.
        """
        return required_core_tags_for_prompt(user_prompt)

    def _base_urls(self) -> tuple[str, ...]:
        base_urls_text = self._str("danbooru_tag_base_urls", "").strip()
        if not base_urls_text:
            return DEFAULT_DONMAI_BASE_URLS
        return tuple(
            item.strip()
            for item in re.split(r"[,;\n]+", base_urls_text)
            if item.strip()
        )

    async def resolve(
        self,
        *,
        llm_content: str,
        user_prompt: str,
        fixed_character: bool,
        candidate_hints: tuple[str, ...] = (),
    ) -> str:
        """Resolve likely character core tags in LLM-generated content.

        Args:
            llm_content: Tags returned by the LLM.
            user_prompt: Original user prompt.
            fixed_character: Whether a fixed character is already selected.
            candidate_hints: Optional evidence candidates proposed from the
                original user request.

        Returns:
            Tags with resolved or inserted core tags when lookup succeeds.
        """
        outcome = await self.resolve_detailed(
            llm_content=llm_content,
            user_prompt=user_prompt,
            fixed_character=fixed_character,
            candidate_hints=candidate_hints,
        )
        return outcome.text

    async def resolve_detailed(
        self,
        *,
        llm_content: str,
        user_prompt: str,
        fixed_character: bool,
        candidate_hints: tuple[str, ...] = (),
    ) -> DanbooruResolveOutcome:
        """Resolve character tags and return request-scoped diagnostics.

        Args:
            llm_content: Tags returned by the prompt LLM.
            user_prompt: Original user request.
            fixed_character: Whether local fixed-character tags own identity.
            candidate_hints: Evidence candidates proposed by the LLM.

        Returns:
            Resolved text, canonical identity anchors, and resolution status.
        """
        if not llm_content or not self._bool("danbooru_core_tag_lookup_enabled", True):
            return DanbooruResolveOutcome(text=llm_content)
        requested = character_resolution_requested(
            llm_content,
            user_prompt=user_prompt if not fixed_character else "",
            candidate_hints=candidate_hints,
        )
        explicit_request = bool(
            not fixed_character
            and character_resolution_requested("", user_prompt=user_prompt)
        )
        timeout = max(
            1.0,
            min(self._float("danbooru_tag_lookup_timeout", 6.0), 20.0),
        )
        max_candidates = max(1, min(self._int("danbooru_tag_max_candidates", 6), 16))
        user_agent = (
            self._str("danbooru_tag_user_agent", DEFAULT_USER_AGENT).strip()
            or DEFAULT_USER_AGENT
        )
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    resolve_core_tags,
                    llm_content,
                    user_prompt=user_prompt,
                    allow_insert=not fixed_character,
                    candidate_hints=tuple(candidate_hints),
                    max_candidates=max_candidates,
                    timeout=min(2.0, timeout),
                    donmai_base_urls=self._base_urls(),
                    user_agent=user_agent,
                    cache=self._cache,
                ),
                timeout=timeout,
            )
        except TimeoutError:
            self.logger.warning(
                "[comfyui_agent] danbooru core tag lookup exceeded total %.1fs budget",
                timeout,
            )
            return DanbooruResolveOutcome(
                text=llm_content,
                status="source_unavailable" if requested else "not_requested",
                candidate_hints=tuple(candidate_hints),
                explicit_request=explicit_request,
            )
        except Exception as exc:
            self.logger.warning(
                "[comfyui_agent] danbooru core tag lookup failed: %s", exc
            )
            return DanbooruResolveOutcome(
                text=llm_content,
                status="source_unavailable" if requested else "not_requested",
                candidate_hints=tuple(candidate_hints),
                explicit_request=explicit_request,
            )
        for old, new, count, source in result.replacements:
            self.logger.info(
                "[comfyui_agent] danbooru core tag resolved: %s -> %s post_count=%s source=%s",
                old,
                new,
                count,
                source,
            )
        for new, count, source in result.inserted:
            self.logger.info(
                "[comfyui_agent] danbooru core tag inserted: %s post_count=%s source=%s",
                new,
                count,
                source,
            )
        for name, count, source in result.verified:
            self.logger.info(
                "[comfyui_agent] danbooru character tag verified: %s post_count=%s source=%s",
                name,
                count,
                source,
            )
        if result.status == "unresolved":
            self.logger.warning(
                "[comfyui_agent] named character tag unresolved candidates=%s",
                ",".join(result.candidate_hints) or "none",
            )
        return DanbooruResolveOutcome(
            text=result.text,
            status=result.status,
            canonical_tag=result.canonical_tag,
            identity_tags=result.identity_tags,
            candidate_hints=result.candidate_hints,
            evidence=result.evidence,
            explicit_request=result.explicit_request,
        )
