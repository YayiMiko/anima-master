# Anima 绘图大师

Anima 绘图大师是 AstrBot 插件：在聊天中发送自然语言，插件整理提示词，交给你自己的 ComfyUI / Anima 工作流生成图片，再把图片发回聊天。

```text
/anm 一个女孩，白色裙子，立绘，简单背景
```

## 快速开始

1. 准备 [AstrBot](https://github.com/AstrBotDevs/AstrBot)、可访问的 [ComfyUI](https://github.com/comfyanonymous/ComfyUI)，以及 Anima 模型、文本编码器和 VAE。
2. 将本仓库安装为 AstrBot 插件。在插件配置页填写 ComfyUI 地址，并选择与 ComfyUI 中完全同名的模型文件：

   ```text
   comfyui_base_url = AstrBot 能访问到的 ComfyUI 地址
   workflow = anima_t2i
   unet_name = Anima 模型文件名
   clip_name = 文本编码器文件名
   vae_name = VAE 文件名
   ```

3. 启动 ComfyUI，在聊天中发送上面的 `/anm` 示例。需要检查连接时发送 `/anm 状态`。

跨机器部署时，ComfyUI 地址必须从 AstrBot 所在机器可访问；本机回环地址只指向 AstrBot 自己。详细步骤见[安装与快速开始](docs/quickstart.md)和[部署拓扑](docs/deployment.md)。

## 能做什么

- 自然语言生图；短描述会被扩展成完整画面，再整理为适合 Anima 的 tags。
- `/anm 多人`生成 2–4 人画面，规划人物位置与互动。
- `/anm 无优化`直接使用给定 tags，不经过 LLM 优化。
- 保存固定角色、画师预设与画风；只有明确点名固定角色时才会调用它。
- 引用图片进行参考、读取图片生成信息，或用视觉模型反推 tags。

图生图需要单独开启；放大与去背景仍在开发中，默认不可用。联网搜索和图片反推也需要各自的服务配置。

## 常用指令

| 指令 | 用途 |
| --- | --- |
| `/anm <描述>` | 自然语言生图 |
| `/anm 多人 <描述>` | 多人画面 |
| `/anm 无优化 <tags>` | 原样 tags 生图 |
| `/anm 状态` | 查看连接与模型状态 |
| `/anm 帮助` | 查看聊天中的常用指令 |

还可以使用 `/anima` 或 `/comfyui` 前缀。完整用法与单次尺寸设置见[指令速查](docs/commands.md)。

## 文档

- [安装与快速开始](docs/quickstart.md)
- [配置说明](docs/configuration.md)
- [提示词、多人、角色与画风](docs/prompting.md)
- [完整指令与尺寸](docs/commands.md)
- [部署拓扑](docs/deployment.md)
- [故障排查](docs/troubleshooting.md)
- [项目结构](docs/architecture.md)
- [可选工作流变体](variants/README.md)

## License

[MIT](LICENSE) © 2026 YayiMiko。图片由用户自己的 ComfyUI 工作流生成；请确认模型与素材的使用权限，并遵守所在平台的规则。
