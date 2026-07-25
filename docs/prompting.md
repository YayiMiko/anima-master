# 提示词与角色画风

## 自然语言模式

普通 `/anm` 会让聊天模型把自然语言整理成 Danbooru tags：

```text
/anm 一个女孩，白色裙子，立绘，简单背景
```

插件会把聊天模型生成的具体内容 tags，与质量词、固定角色、画风词等配置拼接后发送给 ComfyUI。

自然语言主题通常生成 40-55 个内容 tags；复杂服装或复杂构图可增加到约 60 个，硬上限为 65 个。质量词、固定角色、画师组和画风不计入这个上限。

模板会优先保留用户明确指定的主体、花卉、道具、动作、表情和镜头，并限制互相冲突的动作与神态。抽象主题至少保留两个直接可见的主题锚点，避免被常见礼服、花朵或场景素材取代。

## 自动 tags 模式

当输入本身已经主要由逗号分隔的英文 Danbooru tags 组成时，插件会直接整理并拼接最终提示词，不再交给聊天模型重新设计。这样可以避免 DS4 Flash 擅自替换花卉、动作、表情或补充无关服饰。

Tag 串中可以包含一个已保存的中文固定角色名，例如：

```text
/anm 1girl, solo, 狐莉, knee up, standing on one leg, holding sword, point a sword at audience, serious
```

插件会移除角色名文字、拼接该角色的固定 tags，并保留其余输入内容。自动 tags 模式还会保守清理确定性较高的语义冲突，例如互斥视线、完整裸露的重复同义词和 `holding nothing`；持有物会保留基础物件 Tag，并把“剑指观众”等关系规范为模型更容易识别的表达。该模式不会重新设计用户的画面。

自动 tags 模式不要求凑到 40 个；原有内容足够时会保持简洁，但仍受 65 个内容 tags 的硬上限约束。

## 原样 tags 模式

如果你已经写好了完整 tags，可以使用：

```text
/anm 无优化 masterpiece, best quality, 1girl, solo, white dress, simple background
```

这种模式不会调用提示词优化模型。

与自动 tags 模式不同，`无优化` 会完全按原样使用后面的提示词，不再拼接质量词、固定角色、画师组或画风，也不执行内容 Tag 清理。

## 固定角色

在 `fixed_characters` 中添加角色：

```text
狐莉=1 girl, solo, fox girl, white hair, heterochromia, fang, black choker
```

之后在指令中明确提到角色名时，插件会拼接该角色 tags。

没有提到固定角色名时，插件不会自动套用角色。

## 画师与画风 tags

启用画师组后，插件会先拼接当前画师组 tags；当前启用的画风组会继续拼接在画师组之后，用于填写媒介、上色和渲染 tags。画风组通过 `style_presets` 保存，并用 `active_style_preset` 切换。

`default_artist_tags` 仅在没有启用画师组时作为备用画师 tags 使用。

如果某次不想使用画师 tags，可以在指令里写：

```text
不使用默认画风
```

或：

```text
no artist tags
```

## 千代预设

在“千代预设”中选择“千代base”“千代aesthetic”或“千代turbo”后，会应用：

- 把对应的千代画师组写入画师 tags。
- 把狐莉写入固定角色。
- 千代base 使用 `anima_baseV10` 与 CFG 5，并保留当前正负面词。
- 千代aesthetic 使用 `anima_aestheticV11` 与 CFG 3，不注入固定正负面词。
- 千代turbo 使用带 `anima-turbo-lora-v0.2` 的自定义工作流、10 步、CFG 1、`euler/simple`，保留当前正负面词，并启用低 CFG 提示词约束。

狐莉只是可选固定角色，不会默认套用。选择“未启用”后，会重新使用预设启用前的基础配置。

## 图片参考

引用或直接发送图片后，可以使用：

```text
/anm 解析法术
/anm 反推这张图的提示词
```

也可以在生图请求里写“参考这张图”“图中衣服”“同款衣服”等，让插件把图片内容作为参考。
