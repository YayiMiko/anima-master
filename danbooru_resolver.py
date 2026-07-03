from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

try:
    from .danbooru_tags import (
        DEFAULT_DONMAI_BASE_URLS,
        DEFAULT_USER_AGENT,
        TagRecord,
        required_core_tags_for_prompt,
        resolve_core_tags,
    )
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from danbooru_tags import (
        DEFAULT_DONMAI_BASE_URLS,
        DEFAULT_USER_AGENT,
        TagRecord,
        required_core_tags_for_prompt,
        resolve_core_tags,
    )


class DanbooruResolver:
    """Configuration-aware resolver for Danbooru character core tags."""

    def __init__(
        self,
        *,
        logger: Any,
        cache: dict[str, list[TagRecord]],
        get_bool: Callable[[str, bool], bool],
        get_int: Callable[[str, int], int],
        get_float: Callable[[str, float], float],
        get_str: Callable[[str, str], str],
    ):
        """Store Danbooru lookup dependencies.

        Args:
            logger: Logger compatible with AstrBot logger methods.
            cache: Shared Danbooru tag lookup cache.
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
    ) -> str:
        """Resolve likely character core tags in LLM-generated content.

        Args:
            llm_content: Tags returned by the LLM.
            user_prompt: Original user prompt.
            fixed_character: Whether a fixed character is already selected.

        Returns:
            Tags with resolved or inserted core tags when lookup succeeds.
        """
        if not llm_content or not self._bool("danbooru_core_tag_lookup_enabled", True):
            return llm_content
        timeout = max(1.0, min(self._float("danbooru_tag_lookup_timeout", 6.0), 20.0))
        max_candidates = max(1, min(self._int("danbooru_tag_max_candidates", 6), 16))
        user_agent = self._str("danbooru_tag_user_agent", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT
        try:
            result = await asyncio.to_thread(
                resolve_core_tags,
                llm_content,
                user_prompt=user_prompt,
                allow_insert=not fixed_character,
                max_candidates=max_candidates,
                timeout=timeout,
                donmai_base_urls=self._base_urls(),
                user_agent=user_agent,
                cache=self._cache,
            )
        except Exception as exc:
            self.logger.warning("[comfyui_agent] danbooru core tag lookup failed: %s", exc)
            return llm_content
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
        return result.text
