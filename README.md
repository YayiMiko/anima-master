# Anima 绘图大师

Anima 绘图大师是一个 AstrBot 插件，用来把聊天机器人连接到本地 ComfyUI，并针对 Anima 模型提供更顺手的生图体验。

它可以把自然语言需求改写成 Danbooru tags，也可以直接接收你写好的 tags。插件默认不绑定任何私人角色或画风；如果你想快速体验一套可用配置，可以在插件配置里启用内置的“千代预设”。

## 主要功能

- 使用 `/anm` 在聊天中调用本地 ComfyUI 生图。
- 将自然语言需求优化为 Danbooru tags。
- 支持原样 tags 模式，不经过 LLM 改写。
- 支持固定角色、默认画风和画师 tags。
- 支持联网搜索少量参考信息，用于补全角色外观、服装和设定。
- 支持查询 Danbooru / Safebooru 核心角色 tag。
- 支持非 R18 擦边表现力模式，让模型按需求生成更有张力的服装、姿态和镜头 tags。
- 支持解析 PNG 内的生成信息。
- 支持通过视觉模型反推图片提示词。
- 支持去背景和自动启动 ComfyUI。
- 图生图 / 改图功能仍在开发中，默认关闭，不建议作为稳定功能使用。

## 前置要求

你需要先准备好：

- 已安装并可运行的 AstrBot。
- 已安装并可运行的 ComfyUI。
- ComfyUI 中已经放好 Anima 所需模型、文本编码器、VAE 和工作流节点。
- 如果要使用“联网搜索”，需要在 AstrBot 全局配置里填入 Tavily key。
- 如果要使用“反推图片”，需要在 AstrBot 中配置可识图的聊天模型。

默认 ComfyUI 地址是：

```text
http://127.0.0.1:8188
```

## 快速开始

安装插件后，打开 AstrBot WebUI 的插件配置页，至少确认这些配置已经与你本地 ComfyUI 保持一致：

```text
enabled = true
comfyui_base_url = http://127.0.0.1:8188
workflow = 你的工作流预设名
unet_name = 你的模型文件名
clip_name = 你的文本编码器文件名
vae_name = 你的 VAE 文件名
```

然后在聊天里发送：

```text
/anm 一个女孩，白色裙子，立绘，简单背景
```

如果你已经写好了完整 tags，不希望插件改写，可以使用：

```text
/anm 原样 masterpiece, best quality, 1girl, solo, white dress, simple background
```

## 千代预设

`preset_profile` 可以选择：

```text
none
chiyo
```

默认是 `none`，表示插件不自动套用任何私人角色或画风。

选择 `chiyo` 后会启用“千代预设”，它会自动应用：

- Anima 常用基础参数。
- 默认质量词：`masterpiece, best quality, nsfw,`
- 默认画风名称：千代画风。
- 默认画师串：`@yukisiannn, @kani biimu, @ixy, @shnva, @shiromochi sakura, @stmast,`
- 默认 prompt 优化规则：质量词、画师词、具体内容分段拼接。

如果你不想自己写角色 tag，可以试试预设的“狐莉”角色。狐莉不会自动套用；只有当你在指令中明确提到“狐莉”时，插件才会使用这组角色 tags：

```text
1 girl, solo, fox girl, (fox ears, inner ear hair), (white hair, medium hair, hair ornament, hair between eyes), (heterochromia, ice blue eye and amber eye), fang, black choker,
```

启用千代预设后，你仍然可以在配置里覆盖默认画风、质量词或画师串。临时不想用画师串时，也可以在指令里写“不使用默认画风”或 “no artist tags”。

## 自定义固定角色和画风

如果你不使用千代预设，也可以自己配置：

```text
default_style_enabled = true
default_style_name = 你的画风名
default_artist_tags = @artist_a, @artist_b, ...
sensual_mode_enabled = true
```

在 `fixed_characters` 中添加角色：

```json
{
  "角色A": "1girl, solo, ...",
  "角色B": "1boy, solo, ..."
}
```

之后聊天里提到角色名时，插件会优先使用对应的固定角色 tags。
没有明确提到固定角色名时，插件不会自动套用任何角色 tags。

## 擦边表现力模式

`sensual_mode_enabled` 默认开启。用户在提示中写到“涩气、擦边、透明、魅惑、性感、蕾丝、吊带、紧身、露肩、suggestive”等词时，插件会要求 prompt 优化模型保留这种非 R18 边界感，并自行选择合适的 Danbooru tags。

这个模式不会硬编码固定涩气 tags，也不会在用户没有相关要求时主动添加擦边内容。

## 常用指令

```text
/anm
/anm 白色礼服，立绘，简单背景
/anm 原样 masterpiece, best quality, 1girl, solo
/anm 解析法术
/anm 反推这张图的提示词
```

`/anm` 也可以替换为：

```text
/anima
/comfyui
```

## 功能说明

自然语言生图：

```text
/anm 给狐莉穿上蓝白色魔法学院制服，立绘风格
```

插件会先让聊天模型生成 Danbooru tags，再按配置拼接质量词、角色词和画风词，最后发送给 ComfyUI。

原样 tags：

```text
/anm 原样 masterpiece, best quality, 1girl, solo, white background
```

这种模式不会调用 prompt 优化模型，适合已经熟悉 Danbooru tags 的用户。

解析法术：

```text
/anm 解析法术
```

请引用或发送一张本地模型生成的 PNG。插件会尝试读取图片里保存的生成信息。

反推图片：

```text
/anm 反推这张图的提示词
```

请引用或发送图片。插件会调用 AstrBot 当前配置的视觉模型来描述图片元素，并整理成提示词参考。

## 常见问题

### 发送 `/anm` 没反应

先确认聊天平台适配器是否在线，再确认 AstrBot 日志中是否收到消息。如果消息没有进入 AstrBot，通常不是插件问题，而是聊天平台桥接层掉线。

### 提示 ComfyUI 离线

确认 ComfyUI 正在运行，并且 `comfyui_base_url` 与实际地址一致。默认地址是 `http://127.0.0.1:8188`。

### 图片没有发回聊天

检查：

- `send_result_to_chat` 是否为 true。
- 聊天平台是否允许发送本地图片。
- ComfyUI 是否真的产出了图片文件。

### 联网搜索没有生效

联网搜索只会在插件判断需要参考外部资料时启用，并且需要 AstrBot 全局 Tavily key。搜索失败会自动降级为普通 prompt 优化，不会中断生图。

### 新角色画不像

本地模型不一定认识较新的角色或冷门角色。可以尝试：

- 开启联网搜索。
- 在提示里写更具体的外观、服装、配色和标志物。
- 在 `fixed_characters` 中手动添加角色 tags。

### 如何完全自己写 tags

使用“原样”模式：

```text
/anm 原样 你的完整 tags
```

## 开发检查

```powershell
python -m py_compile main.py prompt_builder.py danbooru_tags.py agent_tools/comfyui_agent.py agent_tools/image_prompt_agent.py
rg -n "<你的私人路径>|<你的账号>|<你的 API Key>" .
```
