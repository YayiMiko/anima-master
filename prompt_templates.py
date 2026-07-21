from __future__ import annotations

import hashlib

DEFAULT_LLM_PROMPT_TEMPLATE = """我是一名 AI 画师，请根据以下主题设计大师级提示词。输出应为适用于 Anima 模型的英文 Danbooru tags，而不是自然语言描述。

请先在内部拆解画面，再将结果汇总为一行、使用英文逗号分隔的 tags。不要输出分析过程、标题、Markdown、编号或中文。

内容规则：
- 为画面设计细致的服饰 tags、动作 tags、神态 tags，并根据主题补充必要的环境、背景、氛围、构图、镜头、光影和特效 tags。
- 不要输出角色自身已有的固定设定，例如发色、瞳色、年龄、种族和固定配饰；固定角色词会由程序另行拼接。
- 不要输出 masterpiece、best quality 等前置质量词，也不要输出画师词。
- 用户明确提出的主题、动作、服装和画面重点必须优先保留，不要为了扩写而改变主题。

细节密度：
- 服饰是重点。完整服饰部分通常应包含至少 18 个有效 tags，并可根据服装复杂度继续增加；每一件画面中清晰可见的主要服装，应从款式、剪裁、层次、领口、袖型、腰部、下装、材质、配色、纹样、镶边、扣件、饰品、鞋袜和暴露方式中选取适用细节，每件尽量写出 5-10 个具体短 tag。
- 动作与姿态在适用时通常至少写 8 个 tags，并可根据动作复杂度继续增加，覆盖整体姿势、身体朝向、四肢位置、手部动作、持有物、重心和运动趋势；不要只用 dynamic pose 之类的泛化词代替具体动作。
- 神态在适用时通常至少写 4 个 tags，并可根据表达复杂度继续增加，覆盖视线、眼部状态、嘴部状态、情绪和头部角度；不同神态不要互相冲突。
- 环境、背景、氛围、构图、镜头、光影和特效按主题需要补充，不设总量上限，但只选择真正帮助主题的内容。
- 常规至少输出 55 个互不重复、可见、可生成的内容 tags，可按主题复杂度继续增加，不设数量上限。画面元素单薄时，应优先补充服装结构、动作细节、道具互动、轮廓光和少量设计元素，而不是堆叠同义词。

表达规则：
- 优先使用确实能表达可见画面元素的 Danbooru tags。部分概念直译可能没有有效词条，应拆解为具体形状、材质、纹样、颜色、装饰和视觉感受。例如“苗族少女”可以转化为 ornate silver headdress、silver jewelry、embroidered dress 等可见元素。
- 背景保持简约、有设计感。通常只使用 2-6 个背景相关 tags，可根据主题选择 white background、simple background、character sheet、subtle geometric background、floating particles 等少量元素，不要同时堆叠多个地点、复杂建筑和互相冲突的光源。
- 没有特殊要求时，整体采用可爱、自然、精致的角色表现。可爱主要体现在服装设计、姿态和神态，不要擅自幼化角色。

角色和动态上下文：
{character_rule}
{search_block}
{outfit_transfer_rule}
{reference_rule}
{img2img_rule}
{sensual_rule}

这次，请为我生成以下主题的提示词：
{theme}"""


LEGACY_BUILTIN_TEMPLATE_HASHES = {
    "95d7bfecaa58255d97685577e7ad2ddeac595b6237d3dd623407f077646bd2cc",
    "5e7ec9859914e12a8af8ccbc893d3658bd3c73e01e8fbda32367b1a0d8960e88",
    "1e96479f397110dc67364a929426c43f07b24a0b634af26c8e7d97002aeb27a0",
}


def build_llm_prompt(
    theme: str,
    search_context: str = "",
    fixed_character: bool = False,
    character_name: str = "",
    sensual_mode: bool = False,
    mode: str = "txt2img",
    prompt_builder_template: str = "",
    outfit_transfer_rule: str = "",
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
    if any(
        marker in theme
        for marker in (
            "参考图",
            "引用图",
            "参考图原始正面提示词",
            "参考图视觉反推 tags",
            "引用法术正面提示词",
        )
    ):
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
    configured_template = str(prompt_builder_template or "").strip()
    template = (
        DEFAULT_LLM_PROMPT_TEMPLATE
        if not configured_template or _is_legacy_builtin_template(configured_template)
        else configured_template
    )
    values = {
        "theme": theme,
        "character_rule": character_rule,
        "search_block": search_block,
        "outfit_transfer_rule": str(outfit_transfer_rule or "").strip(),
        "reference_rule": reference_rule,
        "img2img_rule": img2img_rule,
        "style_block": "",
        "sensual_rule": sensual_rule,
    }
    try:
        return template.format(**values)
    except Exception:
        return DEFAULT_LLM_PROMPT_TEMPLATE.format(**values)


def _is_legacy_builtin_template(template: str) -> bool:
    digest = hashlib.sha256(str(template or "").strip().encode("utf-8")).hexdigest()
    return digest in LEGACY_BUILTIN_TEMPLATE_HASHES
