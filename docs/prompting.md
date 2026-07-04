# 提示词与角色画风

## 自然语言模式

普通 `/anm` 会让聊天模型把自然语言整理成 Danbooru tags：

```text
/anm 一个女孩，白色裙子，立绘，简单背景
```

插件会把聊天模型生成的具体内容 tags，与质量词、固定角色、画风词等配置拼接后发送给 ComfyUI。

## 原样 tags 模式

如果你已经写好了完整 tags，可以使用：

```text
/anm 原样 masterpiece, best quality, 1girl, solo, white dress, simple background
```

这种模式不会调用提示词优化模型。

## 固定角色

在 `fixed_characters` 中添加角色：

```text
狐莉=1 girl, solo, fox girl, white hair, heterochromia, fang, black choker
```

之后在指令中明确提到角色名时，插件会拼接该角色 tags。

没有提到固定角色名时，插件不会自动套用角色。

## 画师 tags

填写 `default_artist_tags` 后，插件会把这些画师 tags 拼接到正面提示词中。

如果某次不想使用画师 tags，可以在指令里写：

```text
不使用默认画风
```

或：

```text
no artist tags
```

## 千代预设

打开“一键启用千代预设”后，会应用：

- 把千代画师组写入画师 tags。
- 把狐莉写入固定角色。

狐莉只是可选固定角色，不会默认套用。

## 图片参考

引用或直接发送图片后，可以使用：

```text
/anm 解析法术
/anm 反推这张图的提示词
```

也可以在生图请求里写“参考这张图”“图中衣服”“同款衣服”等，让插件把图片内容作为参考。
