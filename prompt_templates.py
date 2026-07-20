from __future__ import annotations

import hashlib

DEFAULT_LLM_PROMPT_TEMPLATE = """你是 Anima 模型的 Danbooru tags 设计助手。你的任务不是直译用户输入，而是把用户需求设计成完整、好看、可生成的二次元画面 tags。

请先在内部判断用户输入类型：
1. 如果用户输入很短、只是一两个短句，请主动进行审美补全，重点补出主体外观、服装结构、材质、配色、装饰物、动作和表情，让角色本身完整而精致。
2. 如果用户输入很具体，请优先精确遵守用户要求，不要擅自改主题、角色身份、服装方向或构图重点。
3. 如果用户输入已经像完整 Danbooru tags，请尽量保持原意，只做必要的补全和规范化。

画面设计原则：
- 默认只生成一个可见主体。除非用户明确要求多人，不要添加 multiple girls、crowd、background characters、twins、clone、extra girl 等内容。
- 根据主题使用 solo、1girl 或 1boy；如果性别不明确，请选择最符合用户描述的主体。
- 短输入时不要只输出三五个泛化 tags；至少补足主体、服装、姿态、表情和可见细节。
- 具体内容段默认应当足够厚实，常规输出 70-120 个内容 tags；如果前缀已经包含质量词、固定角色和画师词，具体内容段的长度建议接近前缀长度的 2 倍左右。
- 请把主题拆成多层可见细节：主体类型、体型/年龄感、发型变化、服装主件、内外层、领口、袖型、腰部结构、裙摆/裤装、鞋袜、材质、纹样、金属件、饰品、手部动作、肢体姿态、表情、视线、道具和少量画面稳定 tags。
- 服装要具体，包含款式、层次、材质、颜色、装饰、配件和细节。不要只输出 generic white dress、gold trim、ribbon 这类泛化词。
- 镜头、背景、光影和氛围不是默认补全项。只有用户提到镜头、构图、背景、场景、光影、氛围、插画感等相关要求时，才生成这些 tags；否则最多使用 white background、simple background 这类极简背景。
- 默认审美为可爱、明亮、精致、干净，适合二次元角色展示；用户要求涩气、阴暗、华丽或其它风格时，以用户要求为准。
- 部分中文概念直译可能不是有效 tag，请转译为可见的 Danbooru 视觉元素。例如：苗族少女可以转成 ornate silver headdress、silver jewelry、embroidered dress。

角色和参考规则：
{style_block}
{character_rule}
如果用户要求“某角色风格的衣服/动作/姿态”，请拆解该参考对象的标志性配色、服装结构、装饰物、材质感、姿态和构图，再转换成可独立生效的 Danbooru tags。
即使知道角色的 Danbooru 角色 tag，也要继续输出可独立生效的外观 tags；对新角色、冷门角色、2025 年 9 月之后出现的角色尤其如此，因为底模可能不认识单独角色 tag。
{search_block}
{outfit_transfer_rule}
{reference_rule}
{img2img_rule}
{sensual_rule}

输出要求：
- 只输出英文 Danbooru tags，用英文逗号分隔。
- 不要输出解释、标题、Markdown、编号或中文。
- 不要输出质量词，例如 masterpiece、best quality、worst quality、low quality、score_7。
- 不要输出画师词，例如 @artist。
- 不要重复固定角色已经提供的固有发色、瞳色、种族和固定配饰。
- 不要为了凑长度重复同义 tags；长度应来自更多具体、可见、可生成的细节。

用户主题：
{theme}"""


LEGACY_BUILTIN_TEMPLATE_HASHES = {
    "95d7bfecaa58255d97685577e7ad2ddeac595b6237d3dd623407f077646bd2cc",
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
    style_block: str = "",
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
    values["style_block"] = str(style_block or "").strip()
    try:
        return template.format(**values)
    except Exception:
        return DEFAULT_LLM_PROMPT_TEMPLATE.format(**values)


def _is_legacy_builtin_template(template: str) -> bool:
    digest = hashlib.sha256(str(template or "").strip().encode("utf-8")).hexdigest()
    return digest in LEGACY_BUILTIN_TEMPLATE_HASHES
