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
    checks: dict[str, bool] = field(default_factory=dict)
    visible_person_count: int | None = None
    layout: str = ""
    identity_match: str = ""
    identity_confidence: float = 0.0
    interaction_direction: str = ""
    direction_confidence: float = 0.0
    major_anatomy_issue: bool = False
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
    require_facts: bool = False,
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
        require_facts: Whether to retry the vision response once when a
            multi-person fact object is missing.

    Returns:
        A :class:`Verdict` describing the outcome.
    """
    prompt = f"用户的原始画图请求（中文）：\n{user_request}\n\n请审查这张图片。"
    data: dict = {}
    last_error: Exception | None = None
    for attempt in range(2 if require_facts else 1):
        current_prompt = prompt
        if attempt:
            current_prompt += (
                "\n\n上次遗漏了 multi_facts。请重新观察图片并严格按要求的 JSON "
                "结构返回可直接观察到的事实，不要沿用上次结论。"
            )
        try:
            reply = await llm_call(prompt=current_prompt, image_urls=[image_path])
            candidate = _extract_json(reply)
        except Exception as exc:  # noqa: BLE001 - provider may not support vision
            last_error = exc
            continue
        data = candidate
        if not require_facts or isinstance(candidate.get("multi_facts"), dict):
            break
    if not data:
        error = last_error or ValueError("no verification JSON")
        return Verdict(
            passed=True,
            skipped=True,
            error=f"{type(error).__name__}: {error}",
        )

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
    checks_raw = data.get("multi_checks")
    checks = (
        {
            str(key): value
            for key, value in checks_raw.items()
            if isinstance(value, bool)
        }
        if isinstance(checks_raw, dict)
        else {}
    )
    facts_raw = data.get("multi_facts")
    facts = facts_raw if isinstance(facts_raw, dict) else {}
    try:
        visible_person_count = int(facts.get("visible_person_count"))
    except (TypeError, ValueError):
        visible_person_count = None
    layout = str(facts.get("layout") or "").strip().lower()
    identity_match = str(facts.get("identity_match") or "").strip().lower()
    interaction_direction = (
        str(facts.get("interaction_direction") or "").strip().lower()
    )
    try:
        identity_confidence = min(
            1.0, max(0.0, float(facts.get("identity_confidence") or 0.0))
        )
    except (TypeError, ValueError):
        identity_confidence = 0.0
    try:
        direction_confidence = min(
            1.0, max(0.0, float(facts.get("direction_confidence") or 0.0))
        )
    except (TypeError, ValueError):
        direction_confidence = 0.0
    major_anatomy_issue = facts.get("major_anatomy_issue") is True

    # Trust an explicit pass flag, but also enforce the score threshold so a
    # model that says pass=true with a low score still fails.
    explicit_pass = data.get("pass")
    if isinstance(explicit_pass, bool):
        passed = explicit_pass and score >= pass_score
    else:
        passed = score >= pass_score
    return Verdict(
        passed=passed,
        score=score,
        issues=issues,
        fix_hint=fix_hint,
        checks=checks,
        visible_person_count=visible_person_count,
        layout=layout,
        identity_match=identity_match,
        identity_confidence=identity_confidence,
        interaction_direction=interaction_direction,
        direction_confidence=direction_confidence,
        major_anatomy_issue=major_anatomy_issue,
    )
