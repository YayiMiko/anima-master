import re

try:
    from .command_catalog import build_help_text
except ImportError:  # pragma: no cover - direct script-style import.
    from command_catalog import build_help_text

_ROUTE_PREFIX_RE = re.compile(r"^\s*/?", re.IGNORECASE)
_SPACES_RE = re.compile(r"\s+")
_SIZE_VALUE_PATTERN = r"(?P<width>\d{2,5})\s*[xX×*＊✕✖хХ]\s*(?P<height>\d{2,5})"
_SIZE_ALIASES = {
    "方图": 1.0,
    "正方形": 1.0,
    "竖图": 2 / 3,
    "竖版": 2 / 3,
    "横图": 3 / 2,
    "横版": 3 / 2,
    "长竖图": 9 / 16,
    "手机竖屏": 9 / 16,
    "宽屏": 16 / 9,
    "超宽图": 16 / 9,
}

DEFAULT_GENERATION_SIZES = [
    "832x1216",
    "896x1152",
    "1024x1024",
    "1152x896",
    "1216x832",
    "768x1344",
    "1344x768",
    "1024x1536",
]


def help_text(img2img_enabled: bool = False) -> str:
    """Build the chat-visible Anima command help text.

    Args:
        img2img_enabled: Whether to show the img2img/edit command.

    Returns:
        The help text shown in chat.
    """
    return build_help_text(img2img_enabled)


def parse_generation_size(
    text: str, allowed: list[tuple[int, int]]
) -> tuple[str, tuple[int, int] | None, str | None]:
    """Extract one per-request generation size from chat prompt text.

    Args:
        text: Prompt text after the generation command.
        allowed: Width and height pairs allowed by the active configuration.

    Returns:
        Cleaned prompt, selected size, and an optional user-facing error.
    """
    prompt = str(text or "").strip()
    size_match = None
    for pattern in (
        rf"(?<!\S)--(?:尺寸|分辨率)\s*(?:=|＝|:|：)?\s*{_SIZE_VALUE_PATTERN}",
        rf"(?:尺寸|分辨率)\s*(?:为|是|=|＝|:|：)?\s*{_SIZE_VALUE_PATTERN}",
        rf"^\s*{_SIZE_VALUE_PATTERN}\s*[：:,，]",
    ):
        size_match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if size_match:
            break

    selected: tuple[int, int] | None = None
    if size_match:
        selected = int(size_match.group("width")), int(size_match.group("height"))
    else:
        aliases = "|".join(
            re.escape(name) for name in sorted(_SIZE_ALIASES, key=len, reverse=True)
        )
        for pattern in (
            rf"(?<!\S)--(?:尺寸|分辨率)\s*(?:=|＝|:|：)?\s*(?P<alias>{aliases})(?=$|\s|[：:,，])",
            rf"(?:尺寸|分辨率)\s*(?:为|是|=|＝|:|：)?\s*(?P<alias>{aliases})(?=$|\s|[：:,，])",
            rf"^\s*(?P<alias>{aliases})(?=$|\s|[：:,，])\s*[：:,，]?",
        ):
            size_match = re.search(pattern, prompt, flags=re.IGNORECASE)
            if size_match:
                break
        if size_match and allowed:
            target_ratio = _SIZE_ALIASES[size_match.group("alias")]
            selected = min(
                allowed,
                key=lambda size: (
                    abs((size[0] / size[1]) - target_ratio),
                    abs(size[0] * size[1] - 1024 * 1024),
                ),
            )

    if not size_match:
        return prompt, None, None

    cleaned = (prompt[: size_match.start()] + " " + prompt[size_match.end() :]).strip()
    cleaned = re.sub(r"^[\s,，;；:：]+|[\s,，;；:：]+$", "", cleaned)
    cleaned = re.sub(r"([,，;；])\s*[,，;；]+", r"\1", cleaned)
    cleaned = _SPACES_RE.sub(" ", cleaned)
    if selected and allowed and selected not in allowed:
        options = "、".join(f"{width}x{height}" for width, height in allowed)
        return (
            cleaned,
            None,
            f"尺寸 {selected[0]}x{selected[1]} 不可用。可用尺寸：{options}",
        )
    if selected is None:
        return cleaned, None, "当前没有配置可用尺寸。"
    return cleaned, selected, None


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
    prefixes = ("anm", "comfyui", "anima")

    for prefix in prefixes:
        if not lowered.startswith(prefix.lower()):
            continue
        rest = normalized[len(prefix) :].strip(" ，,：:")
        if not rest:
            return "help", ""
        rest_lower = rest.lower()
        action_map = [
            ("help", "help"),
            ("帮助", "help"),
            ("指令表", "help"),
            ("指令", "help"),
            ("菜单", "help"),
            ("status", "status"),
            ("状态", "status"),
            ("diagnose", "diagnose"),
            ("diagnosis", "diagnose"),
            ("诊断", "diagnose"),
            ("部署诊断", "diagnose"),
            ("debug_status", "debug_status"),
            ("debug", "debug_status"),
            ("调试状态", "debug_status"),
            ("调试", "debug_status"),
            ("generate", "generate"),
            ("生图", "generate"),
            ("画图", "generate"),
            ("edit", "edit"),
            ("改图", "edit"),
            ("图生图", "edit"),
            ("风格化", "edit"),
            ("重绘", "edit"),
            ("upscale", "disabled_upscale"),
            ("放大", "disabled_upscale"),
            ("高清修复", "disabled_upscale"),
            ("高清", "disabled_upscale"),
            ("remove_bg", "disabled_remove_bg"),
            ("remove-bg", "disabled_remove_bg"),
            ("抠图", "disabled_remove_bg"),
            ("去背景", "disabled_remove_bg"),
            ("去除背景", "disabled_remove_bg"),
            ("解析法术", "spell"),
            ("法术解析", "spell"),
            ("读取法术", "spell"),
            ("提取提示词", "spell"),
            ("读取提示词", "spell"),
            ("反推提示词", "reverse"),
            ("图片反推", "reverse"),
            ("反推", "reverse"),
            ("添加固定角色", "add_fixed_character"),
            ("添加新的固定角色", "add_fixed_character"),
            ("加入固定角色", "add_fixed_character"),
            ("加入新的固定角色", "add_fixed_character"),
            ("新增固定角色", "add_fixed_character"),
            ("新增新的固定角色", "add_fixed_character"),
            ("新建固定角色", "add_fixed_character"),
            ("新建新的固定角色", "add_fixed_character"),
            ("创建固定角色", "add_fixed_character"),
            ("创建新的固定角色", "add_fixed_character"),
            ("保存固定角色", "add_fixed_character"),
            ("保存新的固定角色", "add_fixed_character"),
            ("固定角色", "add_fixed_character"),
            ("查看画师组", "list_artist_presets"),
            ("列出画师组", "list_artist_presets"),
            ("画师组列表", "list_artist_presets"),
            ("使用画师组", "use_artist_preset"),
            ("启用画师组", "use_artist_preset"),
            ("切换画师组", "use_artist_preset"),
            ("选择画师组", "use_artist_preset"),
            ("删除画师组", "delete_artist_preset"),
            ("移除画师组", "delete_artist_preset"),
            ("设置画师组", "set_artist_tags"),
            ("设置新的画师组", "set_artist_tags"),
            ("新建画师组", "create_artist_preset"),
            ("新建新的画师组", "create_artist_preset"),
            ("创建画师组", "create_artist_preset"),
            ("创建新的画师组", "create_artist_preset"),
            ("创建新画师组", "create_artist_preset"),
            ("保存画师组", "create_artist_preset"),
            ("保存新的画师组", "create_artist_preset"),
            ("画师组", "set_artist_tags"),
            ("追加画师组", "append_artist_tags"),
            ("添加画师组", "append_artist_tags"),
            ("加入画师组", "append_artist_tags"),
            ("加入新的画师组", "append_artist_tags"),
            ("添加角色", "add_fixed_character"),
            ("添加新的角色", "add_fixed_character"),
            ("加入角色", "add_fixed_character"),
            ("加入新的角色", "add_fixed_character"),
            ("新增角色", "add_fixed_character"),
            ("新增新的角色", "add_fixed_character"),
            ("新建角色", "add_fixed_character"),
            ("新建新的角色", "add_fixed_character"),
            ("创建角色", "add_fixed_character"),
            ("创建新的角色", "add_fixed_character"),
            ("保存角色", "add_fixed_character"),
            ("保存新的角色", "add_fixed_character"),
        ]
        for keyword, action in action_map:
            if not rest_lower.startswith(keyword.lower()):
                continue
            prompt = rest[len(keyword) :].strip(" ，,：:")
            return action, prompt
        if prefix.lower() != "anm":
            return None
        return "generate", rest

    natural = re.match(
        r"^(?:用\s*)?(?:anm|comfyui|anima)"
        r"(?:帮我|给我|来)?"
        r"\s*"
        r"(帮助|指令表|指令|菜单|help|状态|status|诊断|部署诊断|diagnose|diagnosis|调试状态|调试|debug_status|debug|画一张|画个|画|生图|生成|改图|重绘|风格化|放大|高清修复|高清|抠图|去背景|去除背景|解析法术|法术解析|读取法术|提取提示词|读取提示词|反推提示词|图片反推|反推)"
        r"\s*(.*)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not natural:
        return None
    verb = natural.group(1)
    prompt = natural.group(2).strip(" ，,：:")
    if verb.lower() == "help" or verb in {"帮助", "指令表", "指令", "菜单"}:
        return "help", prompt
    if verb.lower() == "status" or verb == "状态":
        return "status", prompt
    if verb.lower() in {"diagnose", "diagnosis"} or verb in {"诊断", "部署诊断"}:
        return "diagnose", prompt
    if verb.lower() in {"debug_status", "debug"} or verb in {"调试状态", "调试"}:
        return "debug_status", prompt
    if verb in {"改图", "重绘", "风格化"}:
        return "edit", prompt
    if verb in {"放大", "高清修复", "高清"}:
        return "disabled_upscale", prompt
    if verb in {"抠图", "去背景", "去除背景"}:
        return "disabled_remove_bg", prompt
    if verb in {"解析法术", "法术解析", "读取法术", "提取提示词", "读取提示词"}:
        return "spell", prompt
    if verb in {"反推提示词", "图片反推", "反推"}:
        return "reverse", prompt
    if verb in {"画一张", "画个", "画"}:
        prompt = f"{verb}{prompt}".strip()
    return "generate", prompt
