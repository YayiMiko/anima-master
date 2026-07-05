"""Multimodal self-verification for generated Anima images.

After an image is generated, a vision LLM looks at it and judges whether it
satisfies the user's original request. The verdict drives one optional
prompt-adjusted retry; persistent failure is handed back to the user with a
short explanation.

The actual LLM round-trip is injected as ``llm_call`` so this module stays
free of AstrBot internals and is unit-testable offline. ``llm_call`` must
accept ``(prompt, image_urls)`` and return the model's text reply; a local
file path in ``image_urls`` is encoded to a data URL by the provider layer
(same path used by ``reference_context.reverse_image_tags``).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

LLMCall = Callable[..., Awaitable[str]]

ANIMA_VERIFY_SYSTEM = (
    "你是一个严格但公正的二次元插画审查助手。"
    "你会看到用户的原始画图请求（中文）和一张已生成的图片。"
    "判断图片是否满足请求：主体是否正确、动作/姿态、服饰、场景、整体画风，"
    "以及基本质量（无明显肢体畸形、无脸崩、无乱码文字、构图协调）。\n\n"
    "只输出一个 JSON 对象，不要 Markdown、不要解释：\n"
    "{\n"
    '  "score": 0-10 的整数（10=完全符合）,\n'
    '  "pass": true/false,\n'
    '  "issues": ["用简短中文短语列出具体问题，没问题则空数组"],\n'
    '  "fix_hint": "一句中文，告诉提示词作者下次该怎么改；通过则留空"\n'
    "}\n\n"
    "issues 要具体，例如「少了草帽」「背景是教室不是废土」「多出第三只手」。"
    "图片明显没问题时，pass=true、给高分、issues 和 fix_hint 都留空。"
)


@dataclass
class Verdict:
    """Result of one verification round."""

    passed: bool = True
    score: int = 10
    issues: list[str] = field(default_factory=list)
    fix_hint: str = ""
    skipped: bool = False
    error: str = ""


def _extract_json(text: str) -> dict:
    """Best-effort extraction of a single JSON object from an LLM reply."""
    text = (text or "").strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        if text.count("```") >= 2:
            text = text.split("```", 2)[1]
        else:
            text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


async def verify_image(
    llm_call: LLMCall,
    image_path: str,
    user_request: str,
    pass_score: int = 7,
) -> Verdict:
    """Ask a vision LLM whether ``image_path`` satisfies ``user_request``.

    Degrades safely: if the provider cannot accept images or returns an
    unparseable reply, the verdict is marked ``skipped`` and treated as a pass
    so verification never blocks delivery.

    Args:
        llm_call: Injected async LLM caller ``(prompt, image_urls) -> str``.
        image_path: Local path of the generated image to review.
        user_request: The user's original (Chinese) drawing request.
        pass_score: Minimum score (0-10) required to pass.

    Returns:
        A :class:`Verdict` describing the outcome.
    """
    prompt = f"用户的原始画图请求（中文）：\n{user_request}\n\n请审查这张图片。"
    try:
        reply = await llm_call(prompt=prompt, image_urls=[image_path])
    except Exception as exc:  # noqa: BLE001 - provider may not support vision
        return Verdict(passed=True, skipped=True, error=f"{type(exc).__name__}: {exc}")

    try:
        data = _extract_json(reply)
    except Exception as exc:  # noqa: BLE001 - unparseable judgement -> skip
        return Verdict(passed=True, skipped=True, error=f"{type(exc).__name__}: {exc}")

    try:
        score = int(data.get("score", 10))
    except (TypeError, ValueError):
        score = 10
    issues_raw = data.get("issues") or []
    issues = (
        [str(i).strip() for i in issues_raw if str(i).strip()]
        if isinstance(issues_raw, list)
        else []
    )
    fix_hint = str(data.get("fix_hint") or "").strip()

    # Trust an explicit pass flag, but also enforce the score threshold so a
    # model that says pass=true with a low score still fails.
    explicit_pass = data.get("pass")
    if isinstance(explicit_pass, bool):
        passed = explicit_pass and score >= pass_score
    else:
        passed = score >= pass_score

    return Verdict(passed=passed, score=score, issues=issues, fix_hint=fix_hint)
