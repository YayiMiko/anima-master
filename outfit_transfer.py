from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from .tag_cleaner import normalize_tag_key, split_tags
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from tag_cleaner import normalize_tag_key, split_tags


REFERENCE_MARKERS = (
    "参考引用图",
    "引用图",
    "参考这张图",
    "参考这图",
    "按这张图",
    "照这张图",
    "照着这张图",
    "根据这张图",
    "用这张图",
    "以这张图",
    "图中角色",
    "图里的角色",
    "图中衣服",
    "图里的衣服",
    "同款衣服",
    "参考图片",
    "参考图",
)

SEARCH_MARKERS = (
    "联网",
    "搜索",
    "搜一下",
    "查一下",
    "官方图",
    "设定图",
    "立绘",
    "资料",
)

OUTFIT_MARKERS = (
    "衣服",
    "服装",
    "换装",
    "同款",
    "服装tag",
    "服装 tag",
    "服饰",
)

_DIRECTIVE_SPLIT_RE = re.compile(
    r"(?:参考图视觉反推 tags[：:]|参考图原始正面提示词[：:]|引用法术正面提示词[：:])",
    re.S,
)
_SEARCH_SOURCE_RE = re.compile(
    r"(?:联网搜索|搜索|搜一下|查一下)(?P<subject>.*?)(?:的立绘|立绘|官方图|设定图|服装|衣服|外观|人设)",
    re.S,
)
_DIRECT_SOURCE_RE = re.compile(
    r"(?:穿上|换成|换上|套用|应用)(?P<subject>[\u4e00-\u9fffA-Za-z0-9·_\-]{1,32})的(?:衣服|服装)",
    re.S,
)
_CHARACTER_SOURCE_RE = re.compile(
    r"(?:角色|人物)(?P<subject>[\u4e00-\u9fffA-Za-z0-9·_\-]{1,32})",
    re.S,
)
_SUBJECT_TAIL_TRIM_RE = re.compile(
    r"(?:风格|衣服|服装|立绘|官方图|设定图|外观|人设|解析其?|提取其?|深度思考|应用到.*|为.*穿上.*)$"
)
_NEGATIVE_TARGET_RE = re.compile(r"(?:不要|不用|不使用)(?:固定角色|角色)")
_SPELL_NEGATIVE_SPLIT_RE = re.compile(r"\n\s*引用法术负面提示词[：:]", re.S)
_PRONOUN_SUBJECTS = {
    "她",
    "他",
    "它",
    "她们",
    "他们",
    "它们",
    "这个",
    "那个",
    "该角色",
    "这位角色",
}

_OUTFIT_HINTS = (
    "dress",
    "skirt",
    "gown",
    "apron",
    "apron dress",
    "uniform",
    "robe",
    "cloak",
    "cape",
    "coat",
    "jacket",
    "blouse",
    "shirt",
    "top",
    "bodice",
    "corset",
    "sleeve",
    "sleeves",
    "collar",
    "neckline",
    "hem",
    "ruffle",
    "ruffled",
    "frill",
    "frills",
    "lace",
    "trim",
    "ribbon",
    "bow",
    "sash",
    "obi",
    "belt",
    "brooch",
    "pendant",
    "necklace",
    "choker",
    "tassel",
    "gem",
    "gemstone",
    "jewel",
    "ornament",
    "hair ornament",
    "hair ribbon",
    "hairpin",
    "headdress",
    "hat",
    "cap",
    "bonnet",
    "veil",
    "glove",
    "gloves",
    "stocking",
    "stockings",
    "thighhigh",
    "thighhighs",
    "sock",
    "socks",
    "pantyhose",
    "boots",
    "boot",
    "heels",
    "shoes",
    "shoe",
    "mary janes",
    "laurel",
    "cross motif",
    "church motif",
    "embroider",
    "embroidery",
    "brocade",
    "velvet",
    "silk",
    "satin",
    "chiffon",
    "organza",
    "metal trim",
    "gold trim",
    "silver trim",
    "detached sleeves",
    "puffy short sleeves",
    "long sleeves",
    "short sleeves",
)

_IDENTITY_HINTS = (
    "1girl",
    "1 girl",
    "solo",
    "girl",
    "boy",
    "hair",
    "eye",
    "eyes",
    "eyebrow",
    "eyelash",
    "mouth",
    "face",
    "skin",
    "ears",
    "tail",
    "wing",
    "wings",
    "halo",
    "horn",
    "horns",
    "fang",
    "animal ears",
    "cat ears",
    "fox ears",
    "long hair",
    "short hair",
    "twintails",
    "heterochromia",
    "vampire",
    "angel",
    "demon",
    "maid",
)

_SCENE_HINTS = (
    "background",
    "lighting",
    "light",
    "shadow",
    "angle",
    "full body",
    "upper body",
    "standing",
    "sitting",
    "pose",
    "expression",
    "smile",
    "blush",
    "looking at viewer",
    "white background",
    "simple background",
    "clean background",
)


@dataclass(frozen=True)
class OutfitTransferPlan:
    enabled: bool = False
    source_subject: str = ""
    target_character: str = ""
    source_from_reference: bool = False
    source_from_search: bool = False
    directive_prompt: str = ""


@dataclass(frozen=True)
class OutfitTransferContext:
    """Prompt context containing outfit tags without source identity features."""

    enabled: bool = False
    outfit_summary_source: str = ""
    outfit_summary: str = ""
    forbidden_identity_features: tuple[str, ...] = ()


def build_outfit_transfer_context(
    plan: OutfitTransferPlan, *, prompt: str
) -> OutfitTransferContext:
    """Build outfit-only context from an outfit transfer directive."""
    if not plan.enabled:
        return OutfitTransferContext()
    reference_tags = extract_reference_tag_text(prompt)
    summary = filter_outfit_tags(reference_tags)
    return OutfitTransferContext(
        enabled=True,
        outfit_summary_source="reference_filter" if summary else "directive",
        outfit_summary=summary,
        forbidden_identity_features=("hair", "eyes", "face", "ears", "tail"),
    )


def detect_outfit_transfer(
    prompt: str, fixed_character_name: str = ""
) -> OutfitTransferPlan:
    """Detect the "source outfit -> target character" task pattern."""
    text = str(prompt or "").strip()
    directive = _directive_text(text)
    if not fixed_character_name:
        return OutfitTransferPlan(directive_prompt=directive)
    if _NEGATIVE_TARGET_RE.search(directive):
        return OutfitTransferPlan(directive_prompt=directive)
    if not any(marker in directive for marker in OUTFIT_MARKERS):
        return OutfitTransferPlan(directive_prompt=directive)
    source_subject = _extract_source_subject(directive, fixed_character_name)
    source_from_reference = any(marker in directive for marker in REFERENCE_MARKERS)
    source_from_search = any(marker in directive for marker in SEARCH_MARKERS)
    if not source_subject and not source_from_reference and not source_from_search:
        return OutfitTransferPlan(directive_prompt=directive)
    return OutfitTransferPlan(
        enabled=True,
        source_subject=source_subject,
        target_character=fixed_character_name,
        source_from_reference=source_from_reference,
        source_from_search=source_from_search,
        directive_prompt=directive,
    )


def preferred_search_prompt(plan: OutfitTransferPlan, prompt: str) -> str:
    """Return a search-focused prompt for outfit transfer tasks."""
    if not plan.enabled or not plan.source_from_search:
        return str(prompt or "").strip()
    subject = plan.source_subject or _directive_text(prompt)
    subject = _clean_subject(subject)
    if not subject:
        return str(prompt or "").strip()
    return f"{subject} 角色立绘 服装 外观 配色 饰品 官方图"


def extract_reference_tag_text(prompt: str) -> str:
    """Extract tag-like text from prompt-embedded reference blocks."""
    text = str(prompt or "").strip()
    spell_match = re.search(r"引用法术正面提示词[：:]\s*(.*)\Z", text, flags=re.S)
    if spell_match:
        return _SPELL_NEGATIVE_SPLIT_RE.split(spell_match.group(1), maxsplit=1)[
            0
        ].strip()
    for marker in ("参考图视觉反推 tags", "参考图原始正面提示词"):
        match = re.search(rf"{re.escape(marker)}[：:]\s*(.*)\Z", text, flags=re.S)
        if match:
            return match.group(1).strip()
    return ""


def filter_outfit_tags(text: str, max_tags: int = 48) -> str:
    """Keep only outfit-related tags from a tag-like stream."""
    tags = split_tags(text)
    seen: set[str] = set()
    kept: list[str] = []
    for tag in tags:
        key = normalize_tag_key(tag)
        if not key or key in seen:
            continue
        if _should_drop_tag(key):
            continue
        if not _looks_like_outfit_tag(key):
            continue
        seen.add(key)
        kept.append(tag)
        if len(kept) >= max_tags:
            break
    return ", ".join(kept)


def build_outfit_summary_prompt(
    plan: OutfitTransferPlan,
    *,
    original_prompt: str,
    source_context: str,
) -> str:
    """Build a dedicated LLM prompt for outfit-only extraction."""
    source_subject = plan.source_subject or "参考对象"
    target_character = plan.target_character or "目标角色"
    directive = plan.directive_prompt or str(original_prompt or "").strip()
    return (
        "你是二次元角色服装解析助手。\n"
        "你的任务是从资料中提取一套可迁移给目标角色的服装 tags。\n"
        "只关注服装结构、层次、材质、配色、头饰、胸饰、腰饰、手套、袜鞋、装饰件。\n"
        "不要输出角色身份、名字、发色、瞳色、耳朵、尾巴、角、翅膀、年龄感、体型、表情、动作、背景、质量词或画师词。\n"
        "如果资料不足，可以做保守补全，但必须紧贴已有视觉线索，不要自行改主题。\n"
        "输出 24-60 个英文 Danbooru tags，用英文逗号分隔；不要解释，不要 Markdown。\n\n"
        f"来源对象：{source_subject}\n"
        f"目标角色：{target_character}\n"
        f"用户要求：{directive}\n\n"
        "资料：\n"
        f"{source_context.strip()}"
    )


def build_outfit_transfer_block(plan: OutfitTransferPlan, outfit_summary: str) -> str:
    """Render the prompt-template block for outfit transfer tasks."""
    if not plan.enabled:
        return ""
    lines = [
        "-----------",
        "本次是“来源角色/来源参考 -> 目标固定角色”的服装迁移任务。",
        f"最终主体必须是固定角色“{plan.target_character or '目标角色'}”。",
        "来源对象只用于提供服装结构、材质、配色和装饰；不要复制来源对象的角色身份、发色、瞳色、种族、耳朵、尾巴、角、翅膀、年龄感和体型。",
        "请优先让目标角色穿上来源服装，并保留目标角色自己的身份设定。",
        "如果资料不足，可以补齐服装细节，但不要擅自换成别的服装主题。",
    ]
    if plan.source_subject:
        lines.append(f"来源对象：{plan.source_subject}")
    if outfit_summary:
        lines.extend(
            [
                "来源服装摘要 tags：",
                outfit_summary,
                "请优先围绕这份服装摘要生成最终内容 tags，而不是重新发散到来源对象的整套角色设定。",
            ]
        )
    return "\n".join(lines)


def _directive_text(text: str) -> str:
    parts = _DIRECTIVE_SPLIT_RE.split(str(text or "").strip(), maxsplit=1)
    return parts[0].strip() if parts else str(text or "").strip()


def _extract_source_subject(directive: str, fixed_character_name: str) -> str:
    text = str(directive or "").strip()
    for pattern in (_SEARCH_SOURCE_RE, _DIRECT_SOURCE_RE, _CHARACTER_SOURCE_RE):
        match = pattern.search(text)
        if not match:
            continue
        subject = _clean_subject(match.group("subject"))
        if (
            subject
            and subject not in _PRONOUN_SUBJECTS
            and subject != fixed_character_name
        ):
            return subject
    outfit_match = re.search(
        r"(?P<subject>[\u4e00-\u9fffA-Za-z0-9·_\-]{1,32})的(?:衣服|服装)",
        text,
        flags=re.S,
    )
    if outfit_match:
        subject = _clean_subject(outfit_match.group("subject"))
        if (
            subject
            and subject not in _PRONOUN_SUBJECTS
            and subject != fixed_character_name
        ):
            return subject
    return ""


def _clean_subject(subject: str) -> str:
    text = str(subject or "").strip(" ，,。；;：:\n\t")
    text = _SUBJECT_TAIL_TRIM_RE.sub("", text).strip(" ，,。；;：:\n\t")
    text = re.sub(r"^(?:角色|人物)", "", text).strip()
    return text


def _should_drop_tag(key: str) -> bool:
    if any(hint in key for hint in _IDENTITY_HINTS):
        return True
    if any(hint in key for hint in _SCENE_HINTS):
        return True
    return False


def _looks_like_outfit_tag(key: str) -> bool:
    return any(hint in key for hint in _OUTFIT_HINTS)
