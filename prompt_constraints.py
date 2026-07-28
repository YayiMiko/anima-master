from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

try:
    from .tag_cleaner import join_prompt_parts, normalize_tag_key, split_tags
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from tag_cleaner import join_prompt_parts, normalize_tag_key, split_tags


@dataclass(frozen=True)
class PromptConstraintPlan:
    has_constraints: bool = False
    style_tags: tuple[str, ...] = ()
    priority_tags: tuple[str, ...] = ()
    remove_tags: tuple[str, ...] = ()
    max_content_tags: int = 0
    reason: str = ""


@dataclass(frozen=True)
class PromptConstraintResult:
    content_tags: str
    triggered: bool
    weighted_style_tags: tuple[str, ...] = ()
    priority_tags: tuple[str, ...] = ()
    removed_tags: tuple[str, ...] = ()
    reason: str = ""


def build_constraint_plan_prompt(
    user_prompt: str, llm_content: str, fixed_character_name: str = ""
) -> str:
    """Build the LLM request for a low-CFG prompt constraint plan.

    Args:
        user_prompt: User's original natural-language request.
        llm_content: Candidate tags produced by the prompt builder LLM.
        fixed_character_name: Selected fixed character name, if any.

    Returns:
        Prompt instructing the LLM to return only a structured JSON plan.
    """
    fixed_note = (
        f"The selected fixed character is {fixed_character_name}. "
        "If the user explicitly requests a body part, accessory, pose, or "
        "action, that explicit request overrides generic character-tag stripping."
        if fixed_character_name
        else "No fixed character is selected."
    )
    return f"""You are a visual prompt constraint planner for anime image generation.

Your job is to inspect the user's original request and the candidate Danbooru-style tags, then decide whether the request contains explicit visual constraints that must be protected from dilution.

Do not use generic keyword matching. Reason from the user's intent.
Do not invent a new scene. Only preserve constraints that are explicitly requested or directly necessary for the requested action/object relationship.
{fixed_note}

Return JSON only, with this exact shape:
{{
  "has_constraints": true or false,
  "style_tags": ["unweighted English tags that express a visual medium, rendering method, or art style explicitly requested by the user"],
  "priority_tags": ["English Danbooru-style tags or short English visual phrases to place at the front"],
  "remove_tags": ["candidate tags that conflict with or dilute the user's explicit constraints"],
  "max_content_tags": 0 or an integer from 20 to 80,
  "reason": "short reason"
}}

Rules:
- If there is no explicit constraint, return has_constraints=false and empty arrays.
- If the user explicitly requests a visual medium, rendering method, or art style, put only those style concepts in style_tags. Do not put clothing, mood, pose, character identity, or scene content there.
- style_tags must be plain, unweighted English tags. The caller applies Anima weights.
- priority_tags should be concise and visual. Put action-object relationships first when the user asks for one.
- remove_tags must target candidate tags that are contradictory, distracting, or likely to cause the model to ignore the constraint.
- Use max_content_tags when the candidate is too long for a low-CFG workflow; otherwise use 0.
- Output only JSON. No Markdown.

User request:
{user_prompt}

Candidate tags:
{llm_content}
"""


def parse_constraint_plan(text: str) -> PromptConstraintPlan:
    """Parse and bound a JSON constraint plan returned by the LLM.

    Args:
        text: Raw LLM output.

    Returns:
        Parsed plan, or an empty plan when the output is invalid.
    """
    raw = str(text or "").strip()
    if not raw:
        return PromptConstraintPlan()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
    except Exception:
        return PromptConstraintPlan()
    if not isinstance(data, dict):
        return PromptConstraintPlan()
    style_tags = _string_tuple(data.get("style_tags"))
    priority_tags = _string_tuple(data.get("priority_tags"))
    remove_tags = _string_tuple(data.get("remove_tags"))
    max_content_tags = _bounded_int(data.get("max_content_tags"), 0, 20, 80)
    has_constraints = bool(data.get("has_constraints")) and bool(
        style_tags or priority_tags or remove_tags or max_content_tags
    )
    return PromptConstraintPlan(
        has_constraints=has_constraints,
        style_tags=style_tags,
        priority_tags=priority_tags,
        remove_tags=remove_tags,
        max_content_tags=max_content_tags,
        reason=str(data.get("reason") or "").strip()[:200],
    )


def apply_prompt_constraints(
    content_tags: str, plan: PromptConstraintPlan | None = None
) -> PromptConstraintResult:
    """Apply a low-CFG constraint plan to cleaned content tags.

    Args:
        content_tags: Cleaned LLM-generated content tags.
        plan: Structured constraint plan produced by the LLM.

    Returns:
        Reordered content with priority tags front-loaded and conflicts removed.
    """
    plan = plan or PromptConstraintPlan()
    if not plan.has_constraints:
        return PromptConstraintResult(content_tags=content_tags, triggered=False)

    remove_keys = {
        normalize_tag_key(tag) for tag in plan.remove_tags if normalize_tag_key(tag)
    }
    max_tags = plan.max_content_tags if plan.max_content_tags > 0 else 0
    final_tags: list[str] = []
    seen: set[str] = set()
    removed: list[str] = []
    weighted_style_tags: list[str] = []

    for tag in plan.style_tags:
        for part in split_tags(tag):
            key = normalize_tag_key(part)
            if key and key not in seen:
                seen.add(key)
                weighted_style_tags.append(f"({key}:2)")

    for tag in plan.priority_tags:
        for part in split_tags(tag):
            key = normalize_tag_key(part)
            if key and key not in seen:
                seen.add(key)
                final_tags.append(part)

    for tag in split_tags(content_tags):
        key = normalize_tag_key(tag)
        if not key or key in seen:
            continue
        if _should_remove(key, remove_keys):
            removed.append(tag)
            continue
        seen.add(key)
        final_tags.append(tag)
        if max_tags and len(final_tags) >= max_tags:
            break

    return PromptConstraintResult(
        content_tags=join_prompt_parts(final_tags),
        triggered=True,
        weighted_style_tags=tuple(weighted_style_tags),
        priority_tags=plan.priority_tags,
        removed_tags=tuple(removed[:30]),
        reason=plan.reason,
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and len(text) <= 120:
            result.append(text)
    return tuple(result[:40])


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except Exception:
        return default
    if number <= 0:
        return 0
    return max(minimum, min(number, maximum))


def _should_remove(key: str, remove_keys: set[str]) -> bool:
    if key in remove_keys:
        return True
    return any(
        remove_key and (key in remove_key or remove_key in key)
        for remove_key in remove_keys
    )
