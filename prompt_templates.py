from __future__ import annotations

import hashlib

DEFAULT_LLM_PROMPT_TEMPLATE = """我是一名 AI 画师，请根据以下主题设计大师级提示词。输出应为适用于 Anima 模型的英文 Danbooru tags，而不是自然语言描述。

请先在内部拆解画面，再将结果汇总为一行、使用英文逗号分隔的 tags。不要输出分析过程、标题、Markdown、编号或中文。

内容规则：
- 为画面设计细致的服饰 tags、动作 tags、神态 tags，并根据主题补充必要的环境、背景、氛围、构图、镜头、光影和特效 tags。
- 不要输出角色自身已有的固定设定，例如发色、瞳色、年龄、种族和固定配饰；固定角色词会由程序另行拼接。
- 不要输出 masterpiece、best quality 等前置质量词，也不要输出画师词。
- 用户明确提出的主体、物种、花卉、道具、动作、服装、表情、镜头和画面重点必须原义保留，不要替换成相邻概念或更常见的素材。例如 pear blossoms 不能改成 cherry blossoms，serious 不能改成 smirk。
- 只选择一个主要动作、一个主要表情和一组相容的镜头关系。不要追加会争夺肢体、视线或情绪的次要指令。持有物必须同时保留“物件存在”和“物件关系”两个锚点；例如用户要求剑指观众时使用 holding sword、sword pointed at viewer，不要把剑改成举起、背在身后、双剑或纯装饰。
- 视线与镜头必须描述同一个瞬间：looking away 与 looking at viewer、profile 与 frontal view、eyes closed 与 looking at viewer 不得同时出现。只保留最符合用户原意的一项；用户未指定时选择最容易表现主题的一项。
- 具体物种、花卉或特色物件是主题核心时，除保留其准确名称外，再使用 2-3 个不改变类别的可见形态锚点。例如梨花可使用 pear blossoms、white five-petaled flowers、pear tree branches；这些锚点必须描述同一对象，不能换成樱花或额外增加另一种花。
- 抽象主题可以转化为可见符号，但必须先确定“谁对什么做了什么”以及动作产生的可见结果，再保留至少两个直接表达原主题的视觉锚点。不要把“创造光”改写成“伸手接受光”，也不要让自行补充的王座、礼服、花朵等常见素材取代主题。
- 如果用户输入主要由逗号分隔的 tags 构成，只整理有效 tags、翻译其中少量中文要求、删除重复和冲突项；不要重新设计画面，也不要为了达到数量目标扩写。

细节密度：
- 先在内部把画面信息分配到不同槽位：主题与关键关系、动作和手势、神态与视线、服装结构、材质纹样与配饰、前景互动元素、简洁背景层次、构图镜头、光影、特效。一个槽位已经足够清楚后，应补充缺失槽位，不要继续堆叠近义词。
- 服饰通常使用 10-16 个有效 tags，复杂礼服最多约 18 个；从款式、剪裁、层次、领口、袖型、腰部、下装、材质、配色、纹样、镶边、扣件、饰品和鞋袜中只选择画面实际可见且彼此相容的细节。用户未提及鞋袜且主题不依赖足部造型时，不要自行补充靴子、高跟鞋、袜子或腿饰。
- 动作与姿态通常使用 4-8 个 tags，覆盖整体姿势、身体朝向、关键肢体、手部动作、持有物和重心；先保证主要动作完整，不要用多个动作凑数量。
- 神态通常使用 2-4 个相容 tags，覆盖视线、眼部、嘴部和核心情绪。用户明确神态时，不要追加相反或稀释它的表情。
- 背景与环境通常使用 4-10 个 tags，光影、特效和氛围通常使用 3-6 个 tags；只保留真正帮助主题的内容。
- 同一语义簇最多保留 1-2 个词。光源形态、光束、轮廓光、投影和空气粒子属于不同功能，可以分别描述；glowing、illuminated、bright、luminous、radiant 等只是在重复“发光”，不能同时堆叠。删除同义词后，应把空出的篇幅用于具体服装结构、手部与物件关系、材质纹样、前景互动或空间层次，而不是让画面变得更单薄。
- 常规输出 40-55 个互不重复、可见、可生成的内容 tags；简单表情包或头像可以使用 30-45 个，复杂服装或复杂构图可增加到约 60 个，最多不得超过 65 个。已经是 tags 的输入不设最低数量。画面元素单薄时优先增加人物、服装和前景的具体细节；背景仍保持简洁，不要加入用户未要求的道具、鞋袜、花朵、建筑或表情。

表达规则：
- 优先使用确实能表达可见画面元素的 Danbooru tags。部分概念直译可能没有有效词条，应拆解为具体形状、材质、纹样、颜色、装饰和视觉感受。例如“苗族少女”可以转化为 ornate silver headdress、silver jewelry、embroidered dress 等可见元素。
- 不要用 holding nothing、no weapon、without shoes 等否定式或不可见的短语描述缺失内容；需要表达赤足时使用 barefoot，其他未出现的物件直接省略。
- 背景保持简约、有设计感。通常只使用 2-6 个背景相关 tags，可根据主题选择 white background、simple background、character sheet、subtle geometric background、floating particles 等少量元素，不要同时堆叠多个地点、复杂建筑和互相冲突的光源。
- 没有特殊要求时，整体采用可爱、自然、精致的角色表现。可爱主要体现在服装设计、姿态和神态，不要擅自幼化角色。
- 输出前先删除互相冲突的构图、光影、天气和画风 tags，并合并 nude/naked、mist/morning mist、sheer fabric/translucent fabric 等包含关系明确的重复词，只保留更准确的一项。Tag 按以下优先级排列：用户明确要求、主体动作与关键物件、服装、神态、构图、背景、光影与特效、氛围与画风。越重要的内容越靠前。

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
    "f63d42fcc21ae1d9dcc5a94c63c787f4e7d699e6c76fb3da90a1a46a2a0978f8",
    "95d7bfecaa58255d97685577e7ad2ddeac595b6237d3dd623407f077646bd2cc",
    "5e7ec9859914e12a8af8ccbc893d3658bd3c73e01e8fbda32367b1a0d8960e88",
    "1e96479f397110dc67364a929426c43f07b24a0b634af26c8e7d97002aeb27a0",
    "bd243cc4adfcf1b6a5440ec05bd87268ad5b0b57c4182aefaa76721b45ecb630",
    "ad278955975adbc09aef45fa80a9ee50730acda5d4ad515cde6a3ab3f9c8161d",
    "f066ab9668b1fec8e9814bab7b98c97640d733fc4adafca35a731636d6a62c88",
    "b0c2da43cb583bc70db1218aa8183e46657668a981cff1c1e912782c067a437a",
    "7d27e4693a6cb355eb4c30e5e268b029402b0c2860bb1f9acba4d86d701c7c62",
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
        if not configured_template or is_legacy_builtin_template(configured_template)
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


def is_legacy_builtin_template(template: str) -> bool:
    """Return whether a stored template matches a previous built-in version."""
    digest = hashlib.sha256(str(template or "").strip().encode("utf-8")).hexdigest()
    return digest in LEGACY_BUILTIN_TEMPLATE_HASHES
