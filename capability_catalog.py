from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityEntry:
    """One stable Anima capability exposed to chat commands and/or LLM tools."""

    capability_id: str
    chat_action: str
    bridge_method: str
    llm_tool_name: str | None = None


CAPABILITY_ENTRIES: tuple[CapabilityEntry, ...] = (
    CapabilityEntry("status", "status", "status", "comfyui_status"),
    CapabilityEntry("generate", "generate", "generate", "comfyui_generate"),
    CapabilityEntry("edit", "edit", "edit", "comfyui_edit"),
    CapabilityEntry("upscale", "disabled_upscale", "upscale", None),
    CapabilityEntry("remove_bg", "disabled_remove_bg", "remove_bg", "comfyui_remove_bg"),
    CapabilityEntry("spell", "spell", "extract_prompt", "comfyui_extract_prompt"),
    CapabilityEntry("reverse", "reverse", "reverse_prompt", "comfyui_reverse_prompt"),
)


def capability_ids() -> set[str]:
    """Return stable capability identifiers."""
    return {entry.capability_id for entry in CAPABILITY_ENTRIES}


def chat_actions() -> set[str]:
    """Return chat action names backed by the capability layer."""
    return {entry.chat_action for entry in CAPABILITY_ENTRIES}


def llm_tool_entries() -> list[CapabilityEntry]:
    """Return capabilities exposed as AstrBot LLM tools."""
    return [entry for entry in CAPABILITY_ENTRIES if entry.llm_tool_name]
