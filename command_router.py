import re

try:
    from .command_catalog import (
        COMMAND_PREFIXES,
        build_help_text,
        is_natural_draw_verb,
        keyword_action_pairs,
        natural_action_for,
    )
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from command_catalog import (
        COMMAND_PREFIXES,
        build_help_text,
        is_natural_draw_verb,
        keyword_action_pairs,
        natural_action_for,
    )

_ROUTE_PREFIX_RE = re.compile(r"^\s*/?", re.IGNORECASE)
_SPACES_RE = re.compile(r"\s+")


def help_text(img2img_enabled: bool = False) -> str:
    """Build the chat-visible Anima command help text.

    Args:
        img2img_enabled: Whether to show the img2img/edit command.

    Returns:
        The help text shown in chat.
    """
    return build_help_text(img2img_enabled)


def normalize_route_text(text: str) -> str:
    """Normalize a command-like chat message.

    Args:
        text: Raw chat text.

    Returns:
        Text with the optional leading slash and repeated spaces removed.
    """
    text = _ROUTE_PREFIX_RE.sub("", str(text or "")).strip()
    return _SPACES_RE.sub(" ", text)


def parse_hard_route(text: str) -> tuple[str, str] | None:
    """Parse an Anima hard-route command.

    Args:
        text: Raw chat text or message outline.

    Returns:
        A tuple of action and prompt when the message should be handled by
        Anima, otherwise None.
    """
    normalized = normalize_route_text(text)
    lowered = normalized.lower()

    for prefix in COMMAND_PREFIXES:
        if not lowered.startswith(prefix.lower()):
            continue
        rest = normalized[len(prefix) :].strip(" ，,：:")
        if not rest:
            return "help", ""
        rest_lower = rest.lower()
        for keyword, action in keyword_action_pairs():
            if not rest_lower.startswith(keyword.lower()):
                continue
            prompt = rest[len(keyword) :].strip(" ，,：:")
            if action == "raw_generate":
                prompt = f"{keyword} {prompt}".strip()
                return "generate", prompt
            return action, prompt
        if prefix.lower() != "anm":
            return None
        return "generate", rest

    natural = re.match(
        r"^(?:用\s*)?(?:anm|comfyui|anima)"
        r"(?:帮我|给我|来)?"
        r"\s*"
        r"(帮助|指令表|指令|菜单|help|状态|status|调试状态|调试|debug_status|debug|画一张|画个|画|生图|生成|改图|重绘|风格化|放大|高清修复|高清|抠图|去背景|去除背景|解析法术|法术解析|读取法术|提取提示词|读取提示词|反推提示词|图片反推|反推)"
        r"\s*(.*)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not natural:
        return None
    verb = natural.group(1)
    prompt = natural.group(2).strip(" ，,：:")
    action = natural_action_for(verb)
    if is_natural_draw_verb(verb):
        prompt = f"{verb}{prompt}".strip()
    return action, prompt
