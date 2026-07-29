# Anima 绘图大师

Anima 绘图大师是一个 AstrBot 插件，用来把聊天里的自然语言变成适合本地 ComfyUI / Anima 工作流的 Danbooru tags，并把生成结果发回聊天。

> **0.6.0：** 命名作品角色改用“LLM 候选 + 在线证据”二阶段校正，并从角色单人图提取稳定外观锚点；普通生图与 `/anm 多人` 都会保护已确认的角色身份，并对命名角色自动执行结果校验。

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
- `/anm 多人` 生成 2–4 人画面，并分离各人物身份、位置和互动关系。
- 自然语言自动优化为 Danbooru tags。
- 原样 tags 模式。
- 固定角色、画师组和风格控制。
- 少量联网搜索，用于补充角色外观和服装参考。
- Danbooru / Safebooru 命名角色 tag 证据校正与稳定外观锚点。
- 图片法术解析。
- 视觉模型反推图片提示词。
- 可在 ComfyUI 离线时尝试由 AstrBot 启动 ComfyUI。

图生图、放大和去背景仍处于开发中，当前不作为稳定主功能。

## 快速开始

1. 确认 AstrBot 和 ComfyUI 都能正常运行。
2. 在插件配置页确认 ComfyUI 连接和出图参数。
3. 在聊天中发送 `/anm 一个女孩，白色裙子，立绘，简单背景`。

最低启动清单：

```text
comfyui_base_url = http://127.0.0.1:8188
workflow = anima_t2i
unet_name = 你的 Anima 模型文件名
clip_name = 你的文本编码器文件名
vae_name = 你的 VAE 文件名
```

`127.0.0.1` 指 AstrBot 所在机器。如果 AstrBot 和 ComfyUI 不在同一台设备上，请填写 AstrBot 能访问到的局域网或 Tailscale 地址。

多数用户可以先用绘世启动器、ComfyUI portable 或自己的脚本手动启动 ComfyUI。只有开启“由 AstrBot 拉起 ComfyUI”时，才必须填写 `startup_command`；不开这个功能时，不需要启动命令。

## 常用指令

```text
/anm 一个女孩，白色裙子，立绘，简单背景
/anm 生图 竖图：狐莉站在梨花树下
/anm 生图 少女站在河岸 --尺寸 1216x832
/anm 多人 左边若叶睦抱着吉他，右边千早爱音牵着她的手
/anm 生图 独自旅行的魔法少女
/anm 无优化 masterpiece, best quality, 1girl, solo, white dress, simple background
/anm 解析法术
/anm 反推这张图的提示词
/anm 状态
/anm 调试状态
```

`/anm` 也可以写成 `/anima` 或 `/comfyui`。

每次生图可以单独指定尺寸，不会修改插件的默认设置。支持“方图/正方形”“竖图/竖版”“横图/横版”“长竖图/手机竖屏”“宽屏/超宽图”等说法，插件会从当前“可用尺寸列表”中选择比例最接近的一项。也可以写 `1024x1536：描述` 或在描述末尾添加 `--尺寸 1216x832`；明确尺寸不在可用列表中时，插件会列出可选尺寸，不会静默替换。

自然语言生图默认由聊天模型自由发展统一主题，并丰富服装、姿态、材质、配饰、前景、构图、光影和少量特效。插件仍会保留固定角色身份、人数以及用户明确指定的关键服装、动作、表情和道具。需要完全按现成 tags 生成时，请使用 `/anm 无优化`。

## 配置建议

首次使用时，优先只看这些配置组：

- `ComfyUI 连接`
- `出图参数`
- `自然语言优化`

能稳定出图后，再根据需要调整角色、画师组、联网搜索、由 AstrBot 拉起 ComfyUI 和排查项。

插件配置页会默认把较少使用的项目收进“更多配置”。如果你想做高度自定义，可以对照：

- `docs/advanced-config.example.jsonc`
- `data/config/astrbot_plugin_anima_master_config.example.jsonc`（本机注释模板）

如果你想快速体验千代风格，可以在“千代预设”中选择“千代base”“千代aesthetic”或“千代turbo”。三者都会加入对应的千代画师组，并把“狐莉”加入角色列表；aesthetic 使用 `anima_aestheticV11`、CFG 3，且不注入固定正负面词；turbo 使用 Turbo LoRA 工作流、10 步、CFG 1 和低 CFG 提示词约束。保存并重载插件后，配置页会同步显示实际的模型、参数和提示词；选择“未启用”会恢复启用前的值。狐莉不会自动套用，只有当指令里明确提到“狐莉”时才会使用。

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

如果希望插件在 ComfyUI 离线时尝试启动它，请打开“由 AstrBot 启动 ComfyUI”，并填写一个能直接启动 ComfyUI 服务的 `startup_command`。如果你使用的是绘世启动器，且命令只能打开启动器界面，仍需要在启动器里手动启动 ComfyUI。

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
