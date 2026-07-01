import re
from dataclasses import dataclass
from typing import Any


DEFAULT_QUALITY_TAGS = "masterpiece, best quality,"
OLD_SCORE_QUALITY_TAGS = "masterpiece, best quality, score_7,"
DEFAULT_CHARACTER_TAGS = ""
FIXED_CHARACTER_TAGS: dict[str, str] = {}
DEFAULT_ARTIST_TAGS = ""
CHIYO_PRESET_ALIASES = {"chiyo", "chiyo_preset", "千代", "千代预设", "千代配置"}
CHIYO_STYLE_NAME = "千代画风"
CHIYO_QUALITY_TAGS = "masterpiece, best quality, nsfw,"
CHIYO_NEGATIVE_PROMPT = "worst quality, low quality, artist name"
OLD_SCORE_NEGATIVE_PROMPT = "worst quality, low quality, score_1, score_2, score_3, artist name"
CHIYO_CHARACTER_NAME = "狐莉"
CHIYO_CHARACTER_TAGS = (
    "1 girl, solo, fox girl, (fox ears, inner ear hair), "
    "(white hair, medium hair, hair ornament, hair between eyes), "
    "(heterochromia, ice blue eye and amber eye), fang, black choker,"
)
CHIYO_ARTIST_TAGS = (
    "@yukisiannn, @kani biimu, @ixy, @shnva, "
    "@shiromochi sakura, @stmast,"
)
SENSUAL_MARKERS = (
    'ɬ',
    "色气",
    "涩气",
    "擦边",
    "边界感",
    "性感",
    "诱惑",
    "魅惑",
    "妖艳",
    "撩人",
    "暧昧",
    "挑逗",
    "诱人",
    "透明",
    "透视",
    "黑纱",
    "薄纱",
    "蕾丝",
    "吊带",
    "紧身",
    "露肩",
    "绝对领域",
    "小恶魔",
    "non-r18",
    "non r18",
    "suggestive",
    "seductive",
    "sexy",
    "sensual",
    "alluring",
    "see-through",
    "sheer",
    "transparent",
    "lace",
    "garter",
    "teasing",
)

RAW_PREFIXES = (
    "原样",
    "原样tags",
    "原样tag",
    "原样 tags",
    "原样 tag",
    "直接画",
    "直接出图",
    "直接生图",
    "直接tags",
    "直接tag",
    "直接 tags",
    "直接 tag",
    "不优化",
    "不要优化",
    "跳过优化",
    "跳过提示词优化",
    "raw tags",
    "raw tag",
    "raw",
    "no optimize",
    "no optimization",
    "不用优化",
)

NO_STYLE_MARKERS = (
    "不用我的风格",
    "不要我的风格",
    "不使用我的风格",
    "不要画师词",
    "不用画师词",
    "不加画师词",
    "no artist",
    "no artist tags",
)

NO_CHARACTER_MARKERS = (
    "不要固定角色",
    "不用固定角色",
    "no fixed character",
)

QUALITY_BLOCKLIST = {
    "masterpiece",
    "best quality",
    "score_7",
    "score_6",
    "score_5",
    "score_4",
    "score_3",
    "score_2",
    "score_1",
    "safe",
    "worst quality",
    "low quality",
    "artist name",
}

CHARACTER_BLOCKLIST = {
    "1 girl",
    "1girl",
    "solo",
    "cute",
    "kawaii",
}


@dataclass(frozen=True)
class PromptBuildResult:
    final_prompt: str
    content_tags: str
    raw_mode: bool
    used_fixed_character: bool
    used_default_style: bool
    required_core_tags: tuple[str, ...] = ()
    character_name: str = ""
    used_sensual_mode: bool = False


def apply_config_preset(config: dict[str, Any]) -> dict[str, Any]:
    """Return a config copy with an optional user-facing preset applied."""
    result = dict(config or {})
    preset = str(result.get("preset_profile") or "").strip()
    if preset.lower() not in CHIYO_PRESET_ALIASES and preset not in CHIYO_PRESET_ALIASES:
        return result

    result["preset_profile"] = "chiyo"
    result["default_style_enabled"] = True
    result["prompt_optimize_enabled"] = True
    result["danbooru_core_tag_lookup_enabled"] = bool(
        result.get("danbooru_core_tag_lookup_enabled", True)
    )

    if not str(result.get("default_style_name") or "").strip():
        result["default_style_name"] = CHIYO_STYLE_NAME
    if (
        not str(result.get("quality_prefix") or "").strip()
        or result.get("quality_prefix") == DEFAULT_QUALITY_TAGS
        or result.get("quality_prefix") == OLD_SCORE_QUALITY_TAGS
    ):
        result["quality_prefix"] = CHIYO_QUALITY_TAGS
    if (
        not str(result.get("negative_prompt") or "").strip()
        or result.get("negative_prompt") == OLD_SCORE_NEGATIVE_PROMPT
    ):
        result["negative_prompt"] = CHIYO_NEGATIVE_PROMPT
    if not str(result.get("default_artist_tags") or "").strip():
        result["default_artist_tags"] = CHIYO_ARTIST_TAGS

    fixed_characters = fixed_character_tags(result)
    fixed_characters.setdefault(CHIYO_CHARACTER_NAME, CHIYO_CHARACTER_TAGS)
    result["fixed_characters"] = fixed_characters
    return result


def fixed_character_tags(config: dict[str, Any]) -> dict[str, str]:
    """Return built-in and user-configured fixed character tags."""
    characters = {name: str(tags) for name, tags in FIXED_CHARACTER_TAGS.items()}
    configured = config.get("fixed_characters")
    if isinstance(configured, dict):
        for name, tags in configured.items():
            name_text = str(name or "").strip()
            tags_text = str(tags or "").strip()
            if name_text and tags_text:
                characters[name_text] = tags_text
    elif isinstance(configured, list):
        for item in configured:
            text = str(item or "").strip()
            if not text:
                continue
            separator = "=" if "=" in text else ":"
            if separator not in text:
                continue
            name, tags = text.split(separator, 1)
            name_text = name.strip()
            tags_text = tags.strip()
            if name_text and tags_text:
                characters[name_text] = tags_text
    return characters


def selected_fixed_character(prompt: str, config: dict[str, Any]) -> tuple[str, str] | None:
    """Return the explicitly requested fixed character, if any."""
    text = str(prompt or "")
    text_lower = text.lower()
    if any(marker.lower() in text_lower for marker in NO_CHARACTER_MARKERS):
        return None

    for name, tags in fixed_character_tags(config).items():
        if name and name in text:
            return name, tags
    return None


def strip_raw_prefix(prompt: str) -> tuple[bool, str]:
    text = str(prompt or "").strip()
    lowered = text.lower()
    for prefix in RAW_PREFIXES:
        if lowered.startswith(prefix.lower()):
            return True, text[len(prefix) :].strip(" ，,：:")
    return False, text


def wants_default_style(prompt: str, default: bool = True) -> bool:
    text = str(prompt or "").lower()
    if any(marker.lower() in text for marker in NO_STYLE_MARKERS):
        return False
    return default


def wants_sensual_mode(prompt: str, config: dict[str, Any]) -> bool:
    """Return whether prompt should get extra sensual visual language."""
    if not bool(config.get("sensual_mode_enabled", True)):
        return False
    text = str(prompt or "").lower()
    configured = config.get("sensual_mode_markers")
    markers = SENSUAL_MARKERS
    if isinstance(configured, list) and configured:
        markers = tuple(str(item).lower() for item in configured if str(item).strip())
    return any(marker.lower() in text for marker in markers)


def build_llm_prompt(
    theme: str,
    search_context: str = "",
    fixed_character: bool = False,
    character_name: str = "",
    sensual_mode: bool = False,
    mode: str = "txt2img",
) -> str:
    theme = str(theme or "").strip()
    search_context = str(search_context or "").strip()
    if character_name:
        character_rule = (
            f"最终 prompt 前缀中会拼接固定角色“{character_name}”的角色词，"
            "因此具体内容段不要重复列出该角色的固有发色、瞳色、种族和固定配饰。"
        )
    else:
        character_rule = (
            "用户没有使用固定角色。请为用户指定或描述的主体列出必要的可识别外观特征、年龄感、发色、瞳色、配饰和标志性元素。"
            if not fixed_character
            else "最终 prompt 前缀中会拼接固定角色词，因此具体内容段不要重复列出该角色的固有设定。"
        )
    search_block = ""
    if search_context:
        search_block = f"""
-----------
联网搜索摘要如下。请优先用它理解参考角色、参考服装、动作和视觉符号；不要把网页标题、URL 或出处写进 tags。
{search_context}
"""
    img2img_rule = ""
    if mode == "img2img":
        img2img_rule = """
-----------
这是整图图生图/改图提示词。请围绕目标改动写 tags，并尽量保留原图构图、姿势和背景。
如果用户要求“替换为/换成/改成某角色”，请以新角色为主体列出必要外观特征，不要保留被替换角色的种族、耳朵、尾巴、发色等旧主体设定。
"""
    sensual_rule = ""
    if sensual_mode:
        sensual_rule = """
-----------
本次用户明确要求涩气、透明、魅惑或类似边界感。请由你自行选择合适的 danbooru tags，强化表情、姿态、服装张力和镜头感。
这是非 R18 的擦边表现力需求：不要把它保守改写成普通日常服饰，也不要主动删除透明材质、露肩、紧身、蕾丝、吊带、挑逗表情、暧昧姿势等视觉方向。
不要套用固定模板；优先保持角色一致性、服装要求、可爱感和画面美感。
"""
    return f"""我是一名AI画师，请根据以下内容设计出大师级的提示词段落。应为适用于anima模型的danbooru tags。
为画面搭配服饰tag，动作tag，神态tag等。
{character_rule}
大师之作等前置质量提示词不需要列出。
服装写的更细，每种应当包含5~10短句或更多。
部分词直译很可能不会有有效的tag，请尝试用通感来描绘一些danbooru tag可能缺乏词库的词语。以下是一种例子（你不一定要这样做）：苗族少女→银质华丽头饰
将输出的自然语言汇总到一起。
提示词在背景方面偏简约即可，可以有设计感，但是不要堆叠过多元素，我的模型对于复杂背景的效果不佳。建议根据情况生成白色背景或立绘式白色主题背景，只带有少量元素。
如果用户要求“某角色风格的衣服/动作/姿态”，请先在内部拆解该参考对象的标志性配色、服装结构、装饰物、材质感、姿态和构图，再转换成有效的 danbooru tags。
不要只输出 generic white dress, gold trim, ribbon 这种泛化描述；要保留参考对象最有辨识度的视觉特征。
即使知道角色的 danbooru 角色 tag，也必须继续输出可独立生效的外观 tags；对新角色、冷门角色、2025 年 9 月之后出现的角色尤其如此，因为底模可能不认识单独角色 tag。
{search_block}
{img2img_rule}
{sensual_rule}
-----------
没有特殊要求时，请为我的角色应用可爱风格。注意，这种可爱与用户要求的涩气边界感不冲突。
-----------
这次，请为我生成{theme}主题的提示词。"""


def _split_tags(text: str) -> list[str]:
    cleaned = str(text or "")
    cleaned = re.sub(r"```.*?```", lambda m: m.group(0).strip("`"), cleaned, flags=re.S)
    cleaned = cleaned.replace("，", ",").replace("、", ",").replace(";", ",")
    cleaned = cleaned.replace("\n", ",")
    cleaned = re.sub(r"^(?:positive|prompt|tags|提示词|正向提示词)\s*[:：]", "", cleaned.strip(), flags=re.I)
    parts = [part.strip(" \t\r\n,.;:：") for part in cleaned.split(",")]
    return [part for part in parts if part]


def _normalize_tag_key(tag: str) -> str:
    value = str(tag or "").strip().lower()
    if value.startswith("(") and value.endswith(")") and value.count("(") == 1 and value.count(")") == 1:
        value = value[1:-1].strip()
    value = re.sub(r":\s*[\d.]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def clean_content_tags(
    text: str,
    max_tags: int = 120,
    strip_character_tags: bool = True,
    protected_core_tags: tuple[str, ...] = (),
) -> str:
    tags = _split_tags(text)
    seen: set[str] = set()
    cleaned: list[str] = []
    artist_re = re.compile(r"^@\S+")
    protected = {_normalize_tag_key(tag) for tag in protected_core_tags}
    parenthesized_core_re = re.compile(r"^[a-z0-9_.'-]+_\([a-z0-9_.' -]{2,60}\)$", re.I)
    for tag in tags:
        key = _normalize_tag_key(tag)
        if not key:
            continue
        if key in seen:
            continue
        if key in QUALITY_BLOCKLIST:
            continue
        if strip_character_tags and key in CHARACTER_BLOCKLIST:
            continue
        if protected and parenthesized_core_re.fullmatch(key) and key not in protected:
            continue
        if artist_re.match(tag.strip()):
            continue
        if len(tag) > 80:
            continue
        seen.add(key)
        cleaned.append(tag)
        if len(cleaned) >= max_tags:
            break
    return ", ".join(cleaned)


def join_prompt_parts(parts: list[str]) -> str:
    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for tag in _split_tags(part):
            key = _normalize_tag_key(tag)
            if not key or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
    return ", ".join(tags)


def build_final_prompt(
    *,
    user_prompt: str,
    llm_content: str,
    config: dict[str, Any],
    required_core_tags: tuple[str, ...] = (),
) -> PromptBuildResult:
    config = apply_config_preset(config)
    raw_mode, raw_prompt = strip_raw_prefix(user_prompt)
    if raw_mode:
        final = join_prompt_parts([raw_prompt])
        return PromptBuildResult(
            final_prompt=final,
            content_tags=final,
            raw_mode=True,
            used_fixed_character=False,
            used_default_style=False,
            required_core_tags=(),
            character_name="",
            used_sensual_mode=False,
        )

    fixed_character = selected_fixed_character(user_prompt, config)
    use_character = fixed_character is not None
    use_style = wants_default_style(
        user_prompt,
        bool(config.get("default_style_enabled", False)),
    )
    use_sensual = wants_sensual_mode(user_prompt, config)
    quality = str(config.get("quality_prefix") or DEFAULT_QUALITY_TAGS)
    character_name = ""
    if fixed_character is not None:
        character_name, character = fixed_character
    else:
        character = DEFAULT_CHARACTER_TAGS
    if use_character and not character.strip():
        use_character = False
        character_name = ""
    artist = str(config.get("default_artist_tags") or DEFAULT_ARTIST_TAGS)
    if use_style and not artist.strip():
        use_style = False
    content = clean_content_tags(
        llm_content or user_prompt,
        max_tags=int(config.get("prompt_builder_max_content_tags", 120) or 120),
        strip_character_tags=use_character,
        protected_core_tags=required_core_tags,
    )
    parts = [quality]
    if required_core_tags:
        parts.append(", ".join(required_core_tags))
    if use_character:
        parts.append(character)
    if use_style:
        parts.append(artist)
    parts.append(content or user_prompt)
    return PromptBuildResult(
        final_prompt=join_prompt_parts(parts),
        content_tags=content,
        raw_mode=False,
        used_fixed_character=use_character,
        used_default_style=use_style,
        required_core_tags=tuple(required_core_tags),
        character_name=character_name,
        used_sensual_mode=use_sensual,
    )
