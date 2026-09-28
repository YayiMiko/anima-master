from __future__ import annotations

import re

DEFAULT_PORTRAIT = "default_portrait"
EXPLICIT_SCENE = "explicit_scene"
DEFAULT_PORTRAIT_MARKER = "background_mode_default_portrait"
EXPLICIT_SCENE_MARKER = "background_mode_explicit_scene"

_FRAMING_TAGS = {
    "bust",
    "close-up",
    "cowboy shot",
    "face",
    "headshot",
    "portrait",
    "upper body",
}


def extract_background_mode(text: str) -> tuple[str, str]:
    """Remove the LLM control marker and return its background decision.

    Args:
        text: Raw comma-separated LLM output.

    Returns:
        A pair containing cleaned tags and the normalized background mode. The
        mode is empty when the LLM omitted or contradicted the control marker.
    """
    raw = str(text or "").strip()
    found = {
        marker
        for marker in (DEFAULT_PORTRAIT_MARKER, EXPLICIT_SCENE_MARKER)
        if re.search(rf"(?<![\w]){re.escape(marker)}(?![\w])", raw, flags=re.I)
    }
    cleaned = raw
    for marker in (DEFAULT_PORTRAIT_MARKER, EXPLICIT_SCENE_MARKER):
        cleaned = re.sub(
            rf"\s*,?\s*(?<![\w]){re.escape(marker)}(?![\w])\s*,?\s*",
            ", ",
            cleaned,
            flags=re.I,
        )
    cleaned = re.sub(r"(?:\s*,\s*){2,}", ", ", cleaned).strip(" ,")
    if found == {DEFAULT_PORTRAIT_MARKER}:
        return cleaned, DEFAULT_PORTRAIT
    if found == {EXPLICIT_SCENE_MARKER}:
        return cleaned, EXPLICIT_SCENE
    return cleaned, ""


def apply_default_portrait_tags(text: str) -> str:
    """Ensure a clean white-background character illustration tag set.

    Args:
        text: Cleaned content tags produced by the normal prompt pipeline.

    Returns:
        Tags with compatible portrait framing and the required simple white
        background. Existing explicit framing is preserved.
    """
    tags = [part.strip() for part in str(text or "").split(",") if part.strip()]
    normalized = {tag.lower().replace("_", " ") for tag in tags}
    additions: list[str] = []
    if not normalized.intersection(_FRAMING_TAGS) and "full body" not in normalized:
        additions.append("full body")
    if "centered" not in normalized:
        additions.append("centered")
    for tag in ("simple background", "white background"):
        if tag not in normalized:
            additions.append(tag)
    return ", ".join((*tags, *additions))
