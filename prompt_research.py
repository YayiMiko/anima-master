from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable
from urllib.parse import urlparse

try:
    from astrbot.core.tools.web_search_tools import _tavily_search
except Exception:  # pragma: no cover - web search internals may move upstream.
    _tavily_search = None


WEB_SEARCH_KEYWORDS = (
    "联网",
    "搜索",
    "搜一下",
    "查一下",
    "参考资料",
    "官方图",
    "设定图",
    "资料",
)
DEEP_THINKING_KEYWORDS = (
    "深度思考",
    "认真想",
    "仔细想",
    "严格还原",
    "高度还原",
    "不要跑偏",
    "核心特征",
)

_SPACES_RE = re.compile(r"\s+")
_CJK_TERM_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_ASCII_TERM_RE = re.compile(r"[a-z][a-z0-9_()'-]{3,}", re.I)
_GENERIC_SEARCH_TERMS = {
    "appearance",
    "character",
    "design",
    "official",
    "outfit",
    "visual",
}
_OUTFIT_RELEVANCE_TERMS = {
    "outfit",
    "costume",
    "clothes",
    "uniform",
    "dress",
    "official art",
    "character design",
    "立绘",
    "服装",
    "衣服",
    "外观",
    "人设",
    "设定图",
    "官方图",
    "配色",
}
_LOW_SIGNAL_DOMAINS = (
    "pinterest.",
    "huggingface.co",
    "reddit.com",
    "pixiv.net",
)
_PREFERRED_REFERENCE_DOMAINS = (
    "fandom.com",
    "wiki.gg",
    "bluearchive.wiki",
    "miraheze.org",
)


@dataclass(frozen=True)
class PromptResearchPlan:
    """Research switches selected for one prompt.

    Args:
        use_web_search: Whether web search should run.
        use_deep_thinking: Whether the LLM should use deep thinking options.
        search_reason: Keyword that triggered web search.
        thinking_reason: Keyword that triggered deep thinking.
    """

    use_web_search: bool
    use_deep_thinking: bool
    search_reason: str
    thinking_reason: str


class PromptResearcher:
    """Handle optional prompt research and strategy keyword checks."""

    def __init__(
        self,
        *,
        context: Any,
        logger: Any,
        get_bool: Callable[[str, bool], bool],
        get_int: Callable[[str, int], int],
        get_str: Callable[[str, str], str],
    ):
        """Store dependencies for prompt research.

        Args:
            context: AstrBot plugin context used for per-chat config lookup.
            logger: Logger compatible with AstrBot logger methods.
            get_bool: Config boolean accessor.
            get_int: Config integer accessor.
            get_str: Config string accessor.
        """
        self.context = context
        self.logger = logger
        self._bool = get_bool
        self._int = get_int
        self._str = get_str

    def keyword_reason(self, prompt: str, keywords: tuple[str, ...]) -> str:
        """Return the first keyword that appears in the prompt.

        Args:
            prompt: User prompt.
            keywords: Candidate keywords.

        Returns:
            Matched keyword, or an empty string.
        """
        text = str(prompt or "").lower()
        for keyword in keywords:
            if keyword.lower() in text:
                return keyword
        return ""

    def plan(self, prompt: str) -> PromptResearchPlan:
        """Build the optional research plan for a prompt.

        Args:
            prompt: User prompt.

        Returns:
            Research plan including trigger reasons.
        """
        search_reason = self.keyword_reason(prompt, WEB_SEARCH_KEYWORDS)
        thinking_reason = self.keyword_reason(prompt, DEEP_THINKING_KEYWORDS)
        return PromptResearchPlan(
            use_web_search=bool(search_reason) and self._bool("prompt_builder_web_search_enabled", True),
            use_deep_thinking=bool(thinking_reason) and self._bool("prompt_builder_deep_thinking_enabled", True),
            search_reason=search_reason,
            thinking_reason=thinking_reason,
        )

    def search_query(self, prompt: str) -> str:
        """Build the web search query for a prompt.

        Args:
            prompt: User prompt.

        Returns:
            Query text.
        """
        template = self._str(
            "prompt_builder_search_query_template",
            "{prompt} anime game character outfit pose official art visual design",
        ).strip()
        if "{prompt}" in template:
            return template.replace("{prompt}", prompt).strip()
        return f"{prompt} {template}".strip()

    async def search_context(
        self,
        event: Any,
        prompt: str,
        *,
        search_query_prompt: str | None = None,
    ) -> str:
        """Fetch web search context for a prompt.

        Args:
            event: AstrBot message event for per-chat config lookup.
            prompt: User prompt used for logs and summary text.
            search_query_prompt: Optional prompt override used only for the search query.

        Returns:
            Search context text, or an empty string when unavailable.
        """
        if not self._bool("prompt_builder_web_search_enabled", True):
            return ""
        if _tavily_search is None:
            self.logger.warning("[comfyui_agent] prompt web search unavailable: tavily helper missing")
            return ""

        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            provider_settings = cfg.get("provider_settings", {})
            if not provider_settings.get("websearch_tavily_key", []):
                self.logger.warning("[comfyui_agent] prompt web search skipped: Tavily key not configured")
                return ""
            max_results = max(1, min(self._int("prompt_builder_search_max_results", 5), 8))
            query = self.search_query(search_query_prompt or prompt)
            payload = {
                "query": query,
                "max_results": max_results,
                "include_favicon": False,
                "search_depth": self._str("prompt_builder_search_depth", "advanced") or "advanced",
                "topic": "general",
            }
            if payload["search_depth"] not in {"basic", "advanced"}:
                payload["search_depth"] = "advanced"
            self.logger.info("[comfyui_agent] prompt web search query=%s", query[:300])
            results = await _tavily_search(provider_settings, payload)
            if search_query_prompt:
                results = _prefer_relevant_results(results, query)
        except Exception as exc:
            self.logger.warning("[comfyui_agent] prompt web search failed: %s", exc)
            return ""

        lines = [f"用户主题：{prompt}", "搜索结果："]
        for idx, result in enumerate(results, 1):
            title = str(getattr(result, "title", "") or "").strip()
            url = str(getattr(result, "url", "") or "").strip()
            snippet = str(getattr(result, "snippet", "") or "").strip()
            snippet = _SPACES_RE.sub(" ", snippet)[:500]
            if not title and not snippet:
                continue
            line = f"{idx}. {title}"
            if snippet:
                line += f"\n摘要：{snippet}"
            if url:
                line += f"\nURL：{url}"
            lines.append(line)
        context = "\n".join(lines).strip()
        if len(lines) <= 2:
            return ""
        self.logger.info("[comfyui_agent] prompt web search ok results=%s chars=%s", len(lines) - 2, len(context))
        return context


def _prefer_relevant_results(results: list[Any], query: str) -> list[Any]:
    terms, strong_terms = _relevance_terms(query)
    if not terms and not strong_terms:
        return results
    scored: list[tuple[int, int, Any]] = []
    for result in results:
        title = str(getattr(result, "title", "") or "")
        snippet = str(getattr(result, "snippet", "") or "")
        url = str(getattr(result, "url", "") or "")
        haystack = f"{title}\n{snippet}\n{url}".lower()
        score = _result_relevance_score(haystack, url, terms, strong_terms)
        if score <= 0:
            continue
        strong_hits = sum(1 for term in strong_terms if term in haystack)
        scored.append((score, strong_hits, result))
    if not scored:
        return results
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored]


def _relevance_terms(query: str) -> tuple[list[str], list[str]]:
    text = str(query or "")
    terms: list[str] = []
    strong_terms: list[str] = []
    terms.extend(term.lower() for term in _CJK_TERM_RE.findall(text))
    for term in _ASCII_TERM_RE.findall(text):
        normalized = term.lower().replace("_", " ")
        if normalized in _GENERIC_SEARCH_TERMS:
            continue
        terms.append(normalized)
        terms.append(term.lower())
    if "blue archive" in text.lower():
        terms.append("blue archive")
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        term = term.strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        result.append(term)
        if term not in _OUTFIT_RELEVANCE_TERMS and len(term) >= 3:
            strong_terms.append(term)
    return result, _unique_terms(strong_terms)


def _result_relevance_score(
    haystack: str,
    url: str,
    terms: list[str],
    strong_terms: list[str],
) -> int:
    score = 0
    title_text, _, rest = haystack.partition("\n")
    snippet_text = rest
    domain = urlparse(url).netloc.lower()
    for term in strong_terms:
        if term in title_text:
            score += 8
        elif term in snippet_text:
            score += 4
    for term in terms:
        if term in title_text:
            score += 3
        elif term in snippet_text:
            score += 1
    outfit_hits = sum(1 for term in _OUTFIT_RELEVANCE_TERMS if term in haystack)
    score += min(outfit_hits, 4)
    if strong_terms and not any(term in haystack for term in strong_terms):
        score -= 12
    if any(domain.endswith(preferred) or preferred in domain for preferred in _PREFERRED_REFERENCE_DOMAINS):
        score += 3
    if any(low in domain for low in _LOW_SIGNAL_DOMAINS):
        score -= 4
    return score


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        key = str(term or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result
