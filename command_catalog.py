from __future__ import annotations

from dataclasses import dataclass

COMMAND_PREFIXES = ("anm", "comfyui", "anima")


@dataclass(frozen=True)
class CommandEntry:
    """Chat command metadata used by help text and hard routing."""

    action: str
    keywords: tuple[str, ...]
    help_line: str = ""
    show_in_help: bool = False
    requires_img2img: bool = False


COMMAND_ENTRIES: tuple[CommandEntry, ...] = (
    CommandEntry("help", ("help", "帮助", "指令表", "指令", "菜单")),
    CommandEntry(
        "status", ("status", "状态"), "- /anm 状态：查看 ComfyUI / Anima 状态", True
    ),
    CommandEntry(
        "diagnose",
        ("diagnose", "诊断"),
        "- /anm 诊断：检查服务器、网络和 ComfyUI 连接",
        True,
    ),
    CommandEntry(
        "debug_status",
        ("debug_status", "debug", "调试状态", "调试"),
        "- /anm 调试状态：查看插件关键配置和上次任务摘要",
        True,
    ),
    CommandEntry(
        "generate",
        ("generate", "生图", "画图"),
        "- /anm 生图 <描述>：按描述生成图片",
        True,
    ),
    CommandEntry(
        "multi_person",
        ("多人",),
        "- /anm 多人 <描述>：按人物分组和互动关系生成 2–4 人画面",
        True,
    ),
    CommandEntry(
        "raw_generate",
        ("无优化", "原样"),
        "- /anm 无优化 <tags>：跳过 LLM 优化，直接按 tags 生图",
        True,
    ),
    CommandEntry(
        "edit",
        ("edit", "改图", "图生图", "风格化", "重绘"),
        "- /anm 改图 <要求>：引用图片后整图重绘/风格化",
        True,
        True,
    ),
    CommandEntry("disabled_upscale", ("upscale", "放大", "高清修复", "高清")),
    CommandEntry(
        "disabled_remove_bg", ("remove_bg", "remove-bg", "抠图", "去背景", "去除背景")
    ),
    CommandEntry(
        "spell",
        ("解析法术", "法术解析", "读取法术", "提取提示词", "读取提示词"),
        "- /anm 解析法术：读取图片内嵌的生成信息",
        True,
    ),
    CommandEntry(
        "reverse",
        ("反推提示词", "图片反推", "反推"),
        "- /anm 反推：根据图片内容反推 tags",
        True,
    ),
    CommandEntry(
        "add_fixed_character",
        (
            "添加固定角色",
            "添加新的固定角色",
            "加入固定角色",
            "加入新的固定角色",
            "新增固定角色",
            "新增新的固定角色",
            "新建固定角色",
            "新建新的固定角色",
            "创建固定角色",
            "创建新的固定角色",
            "保存固定角色",
            "保存新的固定角色",
            "固定角色",
            "添加角色",
            "添加新的角色",
            "加入角色",
            "加入新的角色",
            "新增角色",
            "新增新的角色",
            "新建角色",
            "新建新的角色",
            "创建角色",
            "创建新的角色",
            "保存角色",
            "保存新的角色",
        ),
        "- /anm 添加角色 <名称>=<tags>：新增或覆盖角色",
        True,
    ),
    CommandEntry("list_artist_presets", ("查看画师预设", "查看画师组", "列出画师预设", "列出画师组", "画师预设列表", "画师组列表")),
    CommandEntry(
        "use_artist_preset",
        (
            "使用画师预设",
            "使用画师组",
            "启用画师预设",
            "启用画师组",
            "切换画师预设",
            "切换画师组",
            "选择画师预设",
            "选择画师组",
        ),
        "- /anm 切换画师预设 <名称>：切换当前画师预设",
        True,
    ),
    CommandEntry("delete_artist_preset", ("删除画师预设", "删除画师组", "移除画师预设", "移除画师组")),
    CommandEntry("set_artist_tags", ("设置画师预设", "设置画师组", "设置新的画师预设", "设置新的画师组", "画师预设", "画师组")),
    CommandEntry(
        "create_artist_preset",
        (
            "新建画师预设",
            "新建画师组",
            "新建新的画师预设",
            "新建新的画师组",
            "创建画师预设",
            "创建画师组",
            "创建新的画师预设",
            "创建新的画师组",
            "创建新画师预设",
            "创建新画师组",
            "保存画师预设",
            "保存画师组",
            "保存新的画师预设",
            "保存新的画师组",
        ),
        "- /anm 创建画师预设 <名称>=<tags>：保存并启用画师预设",
        True,
    ),
    CommandEntry(
        "append_artist_tags",
        ("追加画师预设", "追加画师组", "添加画师预设", "添加画师组", "加入画师预设", "加入画师组", "加入新的画师预设", "加入新的画师组"),
    ),
)


NATURAL_ACTIONS: dict[str, str] = {
    "help": "help",
    "帮助": "help",
    "指令表": "help",
    "指令": "help",
    "菜单": "help",
    "status": "status",
    "状态": "status",
    "debug_status": "debug_status",
    "debug": "debug_status",
    "调试状态": "debug_status",
    "调试": "debug_status",
    "改图": "edit",
    "重绘": "edit",
    "风格化": "edit",
    "放大": "disabled_upscale",
    "高清修复": "disabled_upscale",
    "高清": "disabled_upscale",
    "抠图": "disabled_remove_bg",
    "去背景": "disabled_remove_bg",
    "去除背景": "disabled_remove_bg",
    "解析法术": "spell",
    "法术解析": "spell",
    "读取法术": "spell",
    "提取提示词": "spell",
    "读取提示词": "spell",
    "反推提示词": "reverse",
    "图片反推": "reverse",
    "反推": "reverse",
}

NATURAL_DRAW_VERBS = {"画一张", "画个", "画"}


def keyword_action_pairs() -> list[tuple[str, str]]:
    """Return route keywords in stable matching order."""
    pairs: list[tuple[str, str]] = []
    for entry in COMMAND_ENTRIES:
        for keyword in entry.keywords:
            pairs.append((keyword, entry.action))
    return pairs


def build_help_text(img2img_enabled: bool = False) -> str:
    """Build the chat-visible Anima command help text."""
    lines = ["Anima 指令表："]
    for entry in COMMAND_ENTRIES:
        if not entry.show_in_help or not entry.help_line:
            continue
        if entry.requires_img2img and not img2img_enabled:
            continue
        if entry.help_line not in lines:
            lines.append(entry.help_line)
    lines.extend(
        [
            "  可在描述开头写“竖图/横图/方图/宽屏”，或写“1024x1536：描述”",
            "  也可在末尾写“--尺寸 1216x832”指定本次尺寸",
            "  自然语言生图默认由 LLM 自主拓展主题并丰富完整画面",
            "",
            "也可以把“anm”换成“comfyui / anima”。",
            "例：/anm 生图 白色礼服，立绘",
        ]
    )
    return "\n".join(lines)


def natural_action_for(verb: str) -> str:
    """Return action for a natural-language command verb."""
    lowered = str(verb or "").lower()
    return NATURAL_ACTIONS.get(lowered) or NATURAL_ACTIONS.get(
        str(verb or ""), "generate"
    )


def is_natural_draw_verb(verb: str) -> bool:
    """Return whether a natural-language verb should be kept in the prompt."""
    return str(verb or "") in NATURAL_DRAW_VERBS
