from __future__ import annotations

try:
    from .prompt_presets import CHIYO_PROMPT_STYLE_V2_ALIASES
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from prompt_presets import CHIYO_PROMPT_STYLE_V2_ALIASES


DEFAULT_LLM_PROMPT_TEMPLATE = """我是一名AI画师，请根据以下内容设计出大师级的提示词段落。应为适用于anima模型的danbooru tags。
为画面搭配服饰tag，动作tag，神态tag等。
{character_rule}
大师之作等前置质量提示词不需要列出。
服装写的更细，每种应当包含5~10短句或更多。
部分词直译很可能不会有有效的tag，请尝试用通感来描绘一些danbooru tag可能缺乏词库的词语。以下是一种例子（你不一定要这样做）：苗族少女→银质华丽头饰
将输出的自然语言汇总到一起。
提示词在背景方面偏简约即可，可以有设计感，但是不要堆叠过多元素，当前模型对于复杂背景的效果不佳。建议根据情况生成白色背景或立绘式白色主题背景，只带有少量元素。
如果用户要求“某角色风格的衣服/动作/姿态”，请先在内部拆解该参考对象的标志性配色、服装结构、装饰物、材质感、姿态和构图，再转换成有效的 danbooru tags。
不要只输出 generic white dress, gold trim, ribbon 这类泛化标签；要保留参考对象最有辨识度的视觉特征。
即使知道角色的 danbooru 角色 tag，也必须继续输出可独立生效的外观 tags；对新角色、冷门角色、2025 年 9 月之后出现的角色尤其如此，因为底模可能不认识单独角色 tag。
除非用户明确要求多角色，否则只为一个可见主体写 tags。根据主题使用 solo、1girl 或 1boy；不要添加背景人物、人群、双胞胎、分身、额外角色或多个角色 tag。
{search_block}
{reference_rule}
{img2img_rule}
{style_block}
{sensual_rule}
-----------
没有特殊要求时，请为目标角色应用可爱风格。注意，这种可爱与用户要求的涩气边界感不冲突。
-----------
这次，请为我生成{theme}主题的提示词。"""


def build_llm_prompt(
    theme: str,
    search_context: str = "",
    fixed_character: bool = False,
    character_name: str = "",
    sensual_mode: bool = False,
    mode: str = "txt2img",
    prompt_builder_style: str = "",
    prompt_builder_template: str = "",
) -> str:
    """Build the prompt sent to the chat LLM for Danbooru tag generation."""
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
    reference_rule = ""
    if any(marker in theme for marker in ("参考图", "引用图", "参考图原始正面提示词", "参考图视觉反推 tags", "引用法术正面提示词")):
        if fixed_character:
            reference_rule = """
-----------
本次带有引用图、图片反推或引用法术上下文，同时用户指定了固定角色。
请把固定角色视为最终画面的主体身份；引用内容只用于提取服装、动作、姿态、构图、镜头、材质、配色和氛围。
不要复制引用对象的角色身份、发色、瞳色、种族、年龄感、耳朵、尾巴、角、翅膀等主体固有设定，除非用户明确要求这些元素作为服装/装饰迁移。
"""
        else:
            reference_rule = """
-----------
本次带有引用图、图片反推或引用法术上下文。
如果用户要求画“图中角色/引用图角色”，请提取主体的可识别外观；如果用户只要求参考衣服、动作或风格，请不要把参考对象身份误当成最终主体。
"""
    sensual_rule = ""
    if sensual_mode:
        sensual_rule = """
-----------
本次用户明确要求涩气、透明、魅惑或类似边界感。请由你自行选择合适的 danbooru tags，强化表情、姿态、服装张力和镜头感。
这是非 R18 的擦边表现力需求：不要把它保守改写成普通日常服饰，也不要主动删除透明材质、露肩、紧身、蕾丝、吊带、挑逗表情、暧昧姿势等视觉方向。
不要套用固定模板；优先保持角色一致性、服装要求、可爱感和画面美感。
"""
    style_block = ""
    style_name = str(prompt_builder_style or "").strip()
    if style_name in CHIYO_PROMPT_STYLE_V2_ALIASES or style_name.lower() in CHIYO_PROMPT_STYLE_V2_ALIASES:
        style_block = """
-----------
提示词生成风格：千代风格2。
请根据用户主题自行判断更适合“立绘式”还是“插画式”，不要机械套固定词。
立绘式更重视清晰单人主体、完整服装轮廓、干净背景、白色或浅色主题背景、少量设计感元素。
插画式更重视画面完成度、镜头感、姿态张力、光影、氛围和角色魅力，但背景仍要克制，避免堆叠复杂场景。
如果用户没有明确指定风格，在不牺牲主题的前提下，优先让画面可爱、明亮、精致、适合二次元角色展示。
这些只是审美方向，不是固定 tags；不要输出画师词、质量词或角色预设词。
"""
    template = str(prompt_builder_template or "").strip() or DEFAULT_LLM_PROMPT_TEMPLATE
    values = {
        "theme": theme,
        "character_rule": character_rule,
        "search_block": search_block,
        "reference_rule": reference_rule,
        "img2img_rule": img2img_rule,
        "style_block": style_block,
        "sensual_rule": sensual_rule,
    }
    try:
        return template.format(**values)
    except Exception:
        return DEFAULT_LLM_PROMPT_TEMPLATE.format(**values)
