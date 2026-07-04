# Anima 绘图大师

Anima 绘图大师是一个 AstrBot 插件，用来把聊天里的自然语言变成适合本地 ComfyUI / Anima 工作流的 Danbooru tags，并把生成结果发回聊天。

![使用示意](docs/images/quickstart-chat.svg)

```text
/anm 一个女孩，白色裙子，立绘，简单背景
```

插件会调用聊天模型优化提示词，再把任务发送给 ComfyUI。你也可以使用“原样”模式直接发送自己写好的 tags。

## 适合谁

- 已经在本地或服务器跑好 ComfyUI 的用户。
- 想在 QQ、群聊或其它 AstrBot 支持的平台里直接生图的用户。
- 想让聊天模型把中文需求整理成 Danbooru tags 的用户。
- 想读取图片生成信息，或反推图片提示词的用户。

## 主要功能

- `/anm` 文生图。
- 自然语言自动优化为 Danbooru tags。
- 原样 tags 模式。
- 固定角色、默认画风、画师 tags。
- 少量联网搜索，用于补充角色外观和服装参考。
- Danbooru / Safebooru 核心角色 tag 校正。
- 图片法术解析。
- 视觉模型反推图片提示词。
- 可在收到绘图请求时按需拉起 ComfyUI。

图生图、放大和去背景仍处于开发中，当前不作为稳定主功能。

## 快速开始

1. 确认 AstrBot 和 ComfyUI 都能正常运行。
2. 在插件配置页填写 ComfyUI 地址、工作流和模型文件名。
3. 在聊天中发送 `/anm 一个女孩，白色裙子，立绘，简单背景`。

最少需要确认这些配置：

```text
comfyui_base_url = http://127.0.0.1:8188
workflow = anima_t2i
unet_name = 你的 Anima 模型文件名
clip_name = 你的文本编码器文件名
vae_name = 你的 VAE 文件名
```

`127.0.0.1` 指 AstrBot 所在机器。如果 AstrBot 和 ComfyUI 不在同一台设备上，请填写 AstrBot 能访问到的局域网或 Tailscale 地址。

## 常用指令

```text
/anm 一个女孩，白色裙子，立绘，简单背景
/anm 原样 masterpiece, best quality, 1girl, solo, white dress, simple background
/anm 解析法术
/anm 反推这张图的提示词
/anm 状态
/anm 调试状态
```

`/anm` 也可以写成 `/anima` 或 `/comfyui`。

## 配置建议

首次使用时，优先只看这些配置组：

- `[01 ComfyUI]`
- `[02 出图]`
- `[03 提示词]`

能稳定出图后，再根据需要调整角色、画风、联网搜索、按需拉起和排查项。

如果你想快速体验千代画风，可以打开“一键启用千代预设”。它会把千代画师组写入画师 tags，并把“狐莉”加入固定角色。狐莉不会自动套用，只有当指令里明确提到“狐莉”时才会使用。

## 详细说明

- [安装与快速开始](docs/quickstart.md)
- [配置说明](docs/configuration.md)
- [部署拓扑](docs/deployment.md)
- [提示词与角色画风](docs/prompting.md)
- [故障排查](docs/troubleshooting.md)

## 常见问题

### 发送 `/anm` 没反应

先确认 AstrBot 是否收到了消息。如果日志里没有新消息，通常是聊天平台适配器或 NapCat/OneBot 连接问题，不是插件问题。

### 提示 ComfyUI 离线

确认 `comfyui_base_url` 填的是 AstrBot 能访问到的 ComfyUI 地址。AstrBot 在服务器时，`127.0.0.1` 指服务器自身。

### 图片没有发回聊天

确认 `send_result_to_chat` 为 true，并检查聊天平台是否允许发送图片。生成文件存在但发送失败时，通常需要看 AstrBot 平台适配器日志。

### 新角色画不像

本地模型不一定认识新角色或冷门角色。可以开启联网搜索，补充更具体的外观、服装、配色和标志物，或在 `fixed_characters` 中手动添加角色 tags。

## 依赖

插件 helper 依赖：

```text
requests
pillow
```

AstrBot 插件管理器通常会处理依赖安装；如果你的环境没有自动安装，请手动安装 `requirements.txt` 中的依赖。
