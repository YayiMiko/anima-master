import re

_ROUTE_PREFIX_RE = re.compile(r"^\s*/?", re.IGNORECASE)
_SPACES_RE = re.compile(r"\s+")


def help_text(img2img_enabled: bool = False) -> str:
    """Build the chat-visible Anima command help text.

    Args:
        img2img_enabled: Whether to show the img2img/edit command.

    Returns:
        The help text shown in chat.
    """
    lines = [
        "Anima 指令表：",
        "- /anm 状态：查看 ComfyUI / Anima 状态",
        "- /anm 调试状态：查看插件关键配置和上次任务摘要",
        "- /anm 生图 <描述>：按描述生成图片",
        "- /anm 无优化 <tags>：跳过 LLM 优化，直接按 tags 生图",
        "- /anm 解析法术：读取图片内嵌的生成信息",
        "- /anm 反推：根据图片内容反推 tags",
        "- /anm 创建画师组 <名称>=<tags>：保存并启用画师组",
        "- /anm 切换画师组 <名称>：切换当前画师组",
        "- /anm 添加角色 <名称>=<tags>：新增或覆盖角色",
    ]
    if img2img_enabled:
        lines.append("- /anm 改图 <要求>：引用图片后整图重绘/风格化")
    lines.extend(["", "也可以把“anm”换成“comfyui / anima”。", "例：/anm 生图 白色礼服，立绘"])
    return "\n".join(lines)


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
        r"(帮助|指令表|指令|菜单|help|状态|status|调试状态|调试|debug_status|debug|画一张|画个|画|生图|生成|改图|重绘|风格化|放大|高清修复|高清|抠图|去背景|去除背景|解析法术|法术解析|读取法术|提取提示词|读取提示词|反推提示词|图片反推|反推)"
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
