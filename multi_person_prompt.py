from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MultiPersonCharacter:
    """One character planned for a multi-person Anima prompt."""

    slot: str
    name: str
    danbooru_candidate: str
    appearance: str
    clothing: str
    expression: str
    pose: str
    props: tuple[str, ...]


@dataclass(frozen=True)
class MultiPersonPlan:
    """Structured multi-person scene plan returned by the prompt LLM."""

    count_tags: tuple[str, ...]
    common_tags: tuple[str, ...]
    characters: tuple[MultiPersonCharacter, ...]
    interactions: tuple[str, ...]
    composition: str


MULTI_PERSON_NEGATIVE_TAGS = (
    "split screen",
    "comic panels",
    "multiple views",
    "character sheet",
    "duplicate characters",
    "cloned character",
    "extra person",
    "extra girl",
    "extra boy",
    "twins",
    "merged bodies",
    "fused characters",
)

_SAFE_SLOTS = {
    "left",
    "right",
    "center",
    "foreground",
    "background",
    "far left",
    "far right",
}

_UNSAFE_COMPOSITION_MARKERS = (
    "split screen",
    "panel",
    "multiple views",
    "alternate views",
    "character sheet",
    "top left",
    "top right",
    "bottom left",
    "bottom right",
)


def build_multi_person_plan_prompt(
    user_prompt: str,
    *,
    fixed_characters: dict[str, str] | None = None,
) -> str:
    """Build the structured planning request for a multi-person scene.

    Args:
        user_prompt: Original user request after command and size parsing.
        fixed_characters: Locally configured character names and authoritative
            defining tags found in the request.

    Returns:
        Prompt asking the LLM for a bounded JSON scene plan.
    """
    fixed_characters = dict(fixed_characters or {})
    fixed_note = (
        "Locally saved characters explicitly mentioned by the user:\n"
        + json.dumps(fixed_characters, ensure_ascii=False, indent=2)
        if fixed_characters
        else "No locally saved character name was detected."
    )
    return f"""Plan one coherent Anima image containing 2 to 4 people.

Use the user's requested identities, count, clothing, expressions, props, positions, and relationships. You may freely design compatible mutable details, background, lighting, and atmosphere when the user leaves them open.

Separate every person into an independent semantic block. Use stable spatial labels such as left, right, center, foreground, or background. For two people, prefer left and right unless the user explicitly requests foreground and background. When the requested action requires overlapping bodies or close physical contact, the slot values are bookkeeping only and must not describe separate regions of the image. Never use top_left, top_right, bottom_left, bottom_right, upper, lower, panel, or "side of the image".

For an existing named character, preserve the user's written name in "name" and provide the most likely Danbooru character tag in "danbooru_candidate". For an original or generic person, leave "danbooru_candidate" empty.

When a person matches one of the locally saved characters below, their saved tags are authoritative. Leave "appearance" empty and do not restate or alter their hair, eyes, species, ears, tail, body type, age, or fixed accessories. Only plan mutable clothing, expression, pose, and props.

Return JSON only with this exact shape:
{{
  "count_tags": ["2girls"],
  "common_tags": ["medium shot", "outdoors"],
  "characters": [
    {{
      "slot": "left",
      "name": "character name from the user",
      "danbooru_candidate": "romanized_character_tag",
      "appearance": "Visible identity traits for a non-fixed character only; empty for a locally saved character.",
      "clothing": "One concise English clothing phrase.",
      "expression": "One concise English expression phrase.",
      "pose": "One concise English body pose that does not repeat the interaction.",
      "props": ["visible prop held or worn by this person"]
    }},
    {{
      "slot": "right",
      "name": "second character name from the user",
      "danbooru_candidate": "romanized_character_tag",
      "appearance": "",
      "clothing": "One concise English clothing phrase.",
      "expression": "One concise English expression phrase.",
      "pose": "One concise English body pose.",
      "props": []
    }}
  ],
  "interactions": [
    "Character A is holding Character B's hand."
  ],
  "composition": "A single unified full-frame composition using one camera view."
}}

Rules:
- Include exactly 2 to 4 character objects.
- count_tags must agree with the number and genders requested by the user.
- common_tags contain only shared scene, framing, camera, lighting, atmosphere, and count tags.
- Do not put character names or character-specific appearance in common_tags.
- For locally saved characters, appearance must be empty and saved defining tags must never be contradicted.
- Do not output quality tags, safety tags, artist tags, Markdown, or explanations.
- Keep character fields and relationships visually concrete.
- Preserve the user's explicit interaction direction and gaze direction.
- Put the complete directed relationship in exactly one interactions entry. Character pose fields must not repeat the relationship.
- Refer to people inside interactions exclusively as Character A, Character B, Character C, or Character D. Never use their names, translated names, or Danbooru tags there.
- Prefer a single coherent moment rather than multiple competing actions.
- composition must use affirmative language to request one unified full-frame camera view.

{fixed_note}

User request:
{user_prompt}
"""


def parse_multi_person_plan(text: str) -> MultiPersonPlan | None:
    """Parse and validate a multi-person JSON plan.

    Args:
        text: Raw LLM completion text.

    Returns:
        A validated plan, or None when the result cannot safely drive generation.
    """
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    raw_characters = data.get("characters")
    if not isinstance(raw_characters, list) or not 2 <= len(raw_characters) <= 4:
        return None
    if any(not isinstance(item, dict) for item in raw_characters):
        return None

    default_slots = {
        2: ("left", "right"),
        3: ("left", "center", "right"),
        4: ("far left", "left", "right", "far right"),
    }[len(raw_characters)]
    proposed_slots = tuple(_normalize_slot(item.get("slot")) for item in raw_characters)
    if (
        any(not slot for slot in proposed_slots)
        or len(set(proposed_slots)) != len(proposed_slots)
        or (
            len(raw_characters) == 2
            and set(proposed_slots)
            not in ({"left", "right"}, {"foreground", "background"})
        )
    ):
        proposed_slots = default_slots

    characters: list[MultiPersonCharacter] = []
    for slot, item in zip(proposed_slots, raw_characters, strict=True):
        characters.append(
            MultiPersonCharacter(
                slot=slot,
                name=_clean_text(item.get("name"), 120),
                danbooru_candidate=_clean_text(item.get("danbooru_candidate"), 160),
                appearance=_clean_text(item.get("appearance"), 500),
                clothing=_clean_text(item.get("clothing"), 400),
                expression=_clean_text(item.get("expression"), 240),
                pose=_clean_text(item.get("pose"), 400),
                props=_string_tuple(item.get("props"), 12, 120),
            )
        )

    count_tags = _string_tuple(data.get("count_tags"), 8, 80)
    common_tags = _string_tuple(data.get("common_tags"), 50, 100)
    interactions = _string_tuple(data.get("interactions"), 1, 500)
    composition = _clean_text(data.get("composition"), 700)
    if any(marker in composition.lower() for marker in _UNSAFE_COMPOSITION_MARKERS):
        composition = ""
    return MultiPersonPlan(
        count_tags=count_tags or (f"{len(characters)}people",),
        common_tags=common_tags,
        characters=tuple(characters),
        interactions=interactions,
        composition=composition,
    )


def render_multi_person_character(
    character: MultiPersonCharacter,
    *,
    alias: str,
    resolved_identity: str = "",
    fixed_tags: str = "",
    grouped_contact: bool = False,
) -> str:
    """Render one character as an Anima-friendly natural-language block.

    Args:
        character: Planned character fields.
        alias: Stable scene alias such as `Character A`.
        resolved_identity: Danbooru-corrected identity tag, when available.
        fixed_tags: Locally saved fixed-character tags, when available.
        grouped_contact: Whether to omit independent spatial placement because
            the characters form one overlapping physical interaction.

    Returns:
        A concise English block with stable spatial ownership.
    """
    label = (
        f"Within the shared close-contact group, {alias}"
        if grouped_contact
        else f"On the {character.slot}, {alias}"
    )
    identity = str(resolved_identity or character.danbooru_candidate or "").strip()
    parts: list[str] = []
    if identity:
        parts.append(f"{label} is {identity}")
    elif character.name:
        parts.append(f"{label} is the character named {character.name}")
    else:
        parts.append(f"{label} is a distinct person")
    if fixed_tags:
        parts.append(f"{alias}'s authoritative defining tags are: {fixed_tags}")
    elif character.appearance:
        parts.append(f"{alias}'s appearance is: {character.appearance}")
    if character.clothing:
        parts.append(f"{alias} wears: {character.clothing}")
    if character.expression:
        parts.append(f"{alias}'s expression is: {character.expression}")
    if character.pose:
        parts.append(f"{alias}'s pose is: {character.pose}")
    if character.props:
        parts.append(f"{alias}'s props are: {', '.join(character.props)}")
    return ". ".join(part.rstrip(" .") for part in parts if part.strip()) + "."


def _string_tuple(value: Any, limit: int, item_limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        text = _clean_text(item, item_limit)
        if text:
            result.append(text)
    return tuple(result[:limit])


def _clean_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def _normalize_slot(value: Any) -> str:
    slot = _clean_text(value, 40).lower().replace("_", " ").replace("-", " ")
    slot = re.sub(r"\s+", " ", slot).strip()
    return slot if slot in _SAFE_SLOTS else ""
