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
    role: str = ""
    visual_label: str = ""
    identity_anchors: tuple[str, ...] = ()
    emphasized_anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class MultiPersonPlan:
    """Structured multi-person scene plan returned by the prompt LLM."""

    count_tags: tuple[str, ...]
    common_tags: tuple[str, ...]
    characters: tuple[MultiPersonCharacter, ...]
    interactions: tuple[str, ...]
    composition: str
    spatial_mode: str
    background_mode: str
    relationship_tag: str = ""


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

_SAFE_SPATIAL_MODES = {
    "shared_contact",
    "shared_scene",
    "explicit_positions",
}


def build_multi_person_plan_prompt(
    user_prompt: str,
    *,
    fixed_characters: dict[str, str] | None = None,
    original_user_prompt: str = "",
) -> str:
    """Build the structured planning request for a multi-person scene.

    Args:
        user_prompt: Original user request after command and size parsing.
        fixed_characters: Locally configured character names and authoritative
            defining tags found in the request.
        original_user_prompt: User text before reference-context expansion.

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

Use the user's requested identities, count, clothing, expressions, props, positions, and relationships. Decide background_mode only from the Original user text below. Reference-image tags, quoted spell tags, and search context in the Expanded request do not count as an explicit background request. Do not invent a scene when the user leaves the background open.

Separate every person into an independent semantic block. Position slots are bookkeeping only and must never describe separate regions, panels, views, or sides of the image. Prefer one shared central group. Use explicit positions only when the user directly asks for left/right or foreground/background placement. Never use top_left, top_right, bottom_left, bottom_right, upper, lower, panel, or "side of the image".

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
      "role": "short semantic role such as rider or supporting girl",
      "visual_label": "distinctive visible label such as white-haired fox girl",
      "identity_anchors": ["3 to 6 short appearance tags"],
      "emphasized_anchors": ["0 to 3 explicitly requested unusual traits"],
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
  "relationship_tag": "holding hands",
  "interactions": [
    "Character A is holding Character B's hand."
  ],
  "spatial_mode": "shared_contact",
  "background_mode": "default_portrait",
  "composition": "A single unified full-frame composition using one camera view."
}}

Rules:
- Include exactly 2 to 4 character objects.
- count_tags must agree with the number and genders requested by the user.
- common_tags contain only shared scene, framing, camera, lighting, atmosphere, and count tags.
- background_mode must be explicit_scene only when the user explicitly requests a location, environment, weather scene, or background. Otherwise it must be default_portrait and common_tags must use full body, centered, simple background, and white background without inventing a location.
- relationship_tag is one short Danbooru-style relationship or action tag and appears immediately after the count tags in the final prompt.
- Do not put character names or character-specific appearance in common_tags.
- role is optional semantic bookkeeping and is not used to identify a person in the final interaction sentence.
- visual_label must be a unique 2 to 6 word visible description derived from identity_anchors, such as "white-haired fox girl" or "silver-haired vampire girl". Do not use names, ordinal labels, rider, supporter, top, bottom, left, or right as visual_label.
- identity_anchors must contain only 3 to 6 concise visible identity traits. For locally saved characters, select them only from the saved defining tags.
- emphasized_anchors may contain at most 3 identity_anchors that the user explicitly requested and that are unusual, contrastive, or likely to be confused between people. Never invent emphasis.
- For locally saved characters, appearance must be empty and saved defining tags must never be contradicted.
- Do not output quality tags, safety tags, artist tags, Markdown, or explanations.
- Keep character fields and relationships visually concrete.
- Preserve the user's explicit interaction direction and gaze direction.
- Put the complete directed relationship in exactly one interactions entry. Character pose fields must not repeat the relationship.
- Refer to people inside interactions exclusively as Character A, Character B, Character C, or Character D. Never use their names, translated names, or Danbooru tags there.
- spatial_mode must be shared_contact for physical interaction, shared_scene for a non-contact group, or explicit_positions only when the user explicitly requests relative positions.
- Prefer a single coherent moment rather than multiple competing actions.
- composition must use affirmative language to request one unified full-frame camera view.

{fixed_note}

Original user text for background intent:
{str(original_user_prompt or user_prompt).strip()}

Expanded request for all other visual details:
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
                role=_clean_text(item.get("role"), 80),
                visual_label=_clean_text(item.get("visual_label"), 100),
                identity_anchors=_string_tuple(item.get("identity_anchors"), 6, 100),
                emphasized_anchors=_string_tuple(
                    item.get("emphasized_anchors"), 3, 100
                ),
            )
        )

    count_tags = _string_tuple(data.get("count_tags"), 8, 80)
    common_tags = _string_tuple(data.get("common_tags"), 50, 100)
    interactions = _string_tuple(data.get("interactions"), 1, 500)
    composition = _clean_text(data.get("composition"), 700)
    spatial_mode = _clean_text(data.get("spatial_mode"), 40).lower()
    background_mode = _clean_text(data.get("background_mode"), 40).lower()
    relationship_tag = _clean_text(data.get("relationship_tag"), 120)
    if spatial_mode not in _SAFE_SPATIAL_MODES:
        spatial_mode = "shared_contact" if interactions else "shared_scene"
    if background_mode not in {"default_portrait", "explicit_scene"}:
        return None
    if any(marker in composition.lower() for marker in _UNSAFE_COMPOSITION_MARKERS):
        composition = ""
    return MultiPersonPlan(
        count_tags=count_tags or (f"{len(characters)}people",),
        common_tags=common_tags,
        characters=tuple(characters),
        interactions=interactions,
        composition=composition,
        spatial_mode=spatial_mode,
        background_mode=background_mode,
        relationship_tag=relationship_tag,
    )


def render_multi_person_character(
    character: MultiPersonCharacter,
    *,
    alias: str,
    resolved_identity: str = "",
    fixed_tags: str = "",
    grouped_contact: bool = False,
    explicit_positions: bool = False,
    identity_anchors: tuple[str, ...] = (),
    include_pose: bool = True,
) -> str:
    """Render one character as an Anima-friendly natural-language block.

    Args:
        character: Planned character fields.
        alias: Stable scene alias such as `Character A`.
        resolved_identity: Danbooru-corrected identity tag, when available.
        fixed_tags: Locally saved fixed-character tags, when available.
        grouped_contact: Whether to omit independent spatial placement because
            the characters form one overlapping physical interaction.
        explicit_positions: Whether the user explicitly requested relative
            placement.
        identity_anchors: Compact validated identity traits for this person.
        include_pose: Whether to include the per-character pose.

    Returns:
        A concise English block with stable spatial ownership.
    """
    label = str(alias or character.visual_label or character.role).strip()
    if explicit_positions and character.slot:
        label = f"{character.slot} {label}"
    identity = str(resolved_identity or character.danbooru_candidate or "").strip()
    details: list[str] = []
    if identity and not fixed_tags:
        details.append(identity)
    if identity_anchors:
        details.extend(identity_anchors)
    elif fixed_tags:
        details.extend(
            part.strip(" ()") for part in fixed_tags.split(",") if part.strip(" ()")
        )
    if not identity_anchors and not fixed_tags and character.appearance:
        details.append(character.appearance)
    if character.clothing:
        details.append(character.clothing)
    if character.expression:
        details.append(character.expression)
    if include_pose and character.pose:
        details.append(character.pose)
    if character.props:
        details.extend(character.props)
    return f"{label}: {', '.join(part for part in details if part)}."


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
