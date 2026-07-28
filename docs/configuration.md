# 配置说明

配置页按使用频率分组。首次使用时，先看“ComfyUI 连接”和“出图参数”。较少使用的项目会收进“更多配置”。

如果你想手动做高度自定义，请对照这些文件：

- `docs/advanced-config.example.jsonc`
- `data/config/astrbot_plugin_anima_master_config.example.jsonc`

真正生效的运行文件是 `data/config/astrbot_plugin_anima_master_config.json`。它是标准 JSON，不能直接写注释。

## 最低启动清单

能发起生图前，至少确认这些配置：

```text
comfyui_base_url = AstrBot 能访问到的 ComfyUI 地址
workflow = 插件支持的工作流预设
unet_name = ComfyUI 中的模型文件名
clip_name = ComfyUI 中的文本编码器文件名
vae_name = ComfyUI 中的 VAE 文件名
```

多数用户可以先用绘世启动器、ComfyUI portable 或自己的脚本手动启动 ComfyUI。如果开启 `auto_start`，还必须填写 `startup_command`。不开 `auto_start` 时，不需要填写启动命令。

这些项目主要分布在“ComfyUI 连接”和“出图参数”两个配置组里。

## 预设

- `reset_to_defaults`：一键恢复默认配置。打开并保存后，仅在下一次插件加载时执行一次，完成后会自动关闭。
- `chiyo_preset`：选择千代预设。可选 `未启用` / `千代base` / `千代aesthetic` / `千代turbo`（配置值分别为空、`base`、`aesthetic`、`turbo`）。

未启用时使用当前配置。选择任一千代预设后，都会把对应的千代画师组写入画师 tags，并把狐莉加入固定角色。狐莉不是默认角色，只有指令里明确提到“狐莉”时才会使用。

各预设差异：

| 预设 | UNet | CFG | 质量词 / 负面词 |
| --- | --- | --- | --- |
| 千代base | `anima_baseV10.safetensors` | 5 | 使用当前配置的质量词与负面词 |
| 千代aesthetic | `anima_aestheticV11.safetensors` | 3 | 都不注入 |
| 千代turbo | `anima_baseV10.safetensors` + `anima-turbo-lora-v0.2.safetensors` | 1 | 使用当前配置的质量词与负面词 |

千代turbo 使用 `variants/turbo/workflows/comfyui_00051_api.json`，固定为 10 步、`euler`、`simple`，并启用面向 CFG 1 的二次 LLM 约束规划。该规划会前置明确要求、删除冲突或稀释 Tag、为明确要求的画风加权，并可把内容段进一步限制在 20–80 个 Tag；存在明确约束时不会触发普通的长度重试。

首次启用预设时，插件会在插件数据目录保存模型、生成参数、正负面提示词和自定义工作流字段的基础快照，再把预设值回写到配置页；内部快照不会显示为配置项。保存并重载插件后刷新页面即可看到实际值。切换预设时会从同一份基础快照重新计算，选择“未启用”则恢复启用前的值。旧配置里的 `chiyo_preset_enabled` 与旧画师组名“千代风格”“千代画风”仍可识别，并会迁移到千代base。已有的“千代turbo”和“千代turbo2”画师组会保留；千代turbo 预设优先使用同名画师组，不会覆盖用户保存的内容。

## ComfyUI 连接

- `comfyui_base_url`：AstrBot 能访问到的 ComfyUI 地址。
- `workflow`：工作流预设，默认使用 `anima_t2i`。
- `custom_workflow_enabled`：是否改用自定义 ComfyUI API 工作流；普通版默认关闭。
- `custom_workflow_path`：自定义工作流 JSON 路径；千代turbo 会自动使用 `variants/turbo/` 中的工作流。
- `timeout`：等待生成完成的最长时间。
- `storage_retention_days`：输入图片、输出图片和逐任务状态文件的保留天数；设为 `0` 可关闭按时间清理。
- `manifest_max_records`：输入图片清单压缩后保留的最大有效记录数，默认 `5000`。
- `poll_interval`：查询 ComfyUI 生成状态的间隔。

`custom_workflow_override_parameters` 默认关闭。关闭时保留自定义工作流中的尺寸、采样步数、CFG、采样器和调度器；Turbo 工作流应保持关闭。需要统一使用插件出图参数时再开启。

`127.0.0.1` 指 AstrBot 所在机器。跨机器部署时，请填写局域网或 Tailscale 地址。

## 出图

- `width` / `height`：默认尺寸。
- `allowed_sizes`：允许的尺寸列表。
- `steps`：采样步数。
- `cfg`：CFG 强度。
- `sampler_name` / `scheduler`：采样器和调度器。
- `unet_name` / `clip_name` / `vae_name`：模型文件名。
- `quality_prefix`：固定拼接在正面提示词前面的质量词。
- `negative_prompt`：默认负面提示词。

模型文件名只填文件名，不填路径。

## 提示词

- `prompt_optimize_enabled`：是否让聊天模型优化自然语言提示词。
- `prompt_builder_provider_id`：指定用于优化提示词的模型。留空时使用当前会话主模型。
- `prompt_builder_max_tokens`：提示词优化模型最大输出长度。
- `prompt_builder_max_content_tags`：LLM 内容段的硬上限，默认 65；不计算质量词、固定角色、画师组和画风。自然语言主题通常以 40–55 个内容 Tag 为目标，简单表情包或头像可以使用 30–45 个，复杂服装或构图约 60 个；已经是 Tag 串的输入不设最低数量。普通模式会在去除较多同义词后尝试一次按缺失画面槽位补全。
- `prompt_builder_template`：主提示词模板。

通常不需要一开始就改 `prompt_builder_template`。如果想改变插件如何理解中文需求，再调整它。

## 联网与 tag 查询

- `prompt_builder_web_search_enabled`：允许在需要时联网搜索。
- `prompt_builder_search_query_template`：搜索查询模板。
- `danbooru_core_tag_lookup_enabled`：校正少量疑似角色核心 tag。Donmai 不可用时会自动回退到 Safebooru 只读 DAPI。
- `danbooru_tag_base_urls`：优先使用的 Donmai tag API 地址。

联网搜索需要 AstrBot 全局 Tavily key。搜索失败会自动降级，不会中断生图。

## 角色与画风

- `fixed_characters`：固定角色预设。
- `default_artist_tags`：未启用画师组时使用的备用画师 tags。
- `style_tags`（画风）：独立于画师组的画风 tags，拼接在当前画师组之后。
- `style_presets`：已保存的画风列表。
- `active_style_preset`：当前启用的画风；留空时使用 `style_tags`。
- `sensual_mode_enabled`：涩气表现力优化。
- `sensual_mode_markers`：触发涩气表现力优化的关键词。

固定角色格式：

```text
角色名=danbooru tags
```

## 实验功能

图生图、放大和去背景仍在开发中。配置项保留给后续版本使用，不建议作为稳定功能依赖。

## 发送与权限

- `send_result_to_chat`：是否把图片发回聊天。
- `max_send_images`：最多发送几张。
- `admin_only`：是否仅管理员可用。
- `allowed_sender_ids`：允许使用的用户 ID 列表。

## 由 AstrBot 启动 ComfyUI

`auto_start` 不是开机自启。它只会在 ComfyUI 离线且收到绘图请求时，在 AstrBot 所在机器上执行 `startup_command`。

不开 `auto_start` 时，不需要填写 `startup_command`，但需要你先手动启动 ComfyUI。开启 `auto_start` 后，`startup_command` 就是必填项。

`startup_command` 必须是能直接启动 ComfyUI 服务的命令。ComfyUI portable 常见是 `run_nvidia_gpu.bat` 一类脚本；绘世启动器如果只是打开启动器界面，不等于 ComfyUI 服务已经启动。

如果 ComfyUI 在另一台机器，AstrBot 不会直接启动远端 ComfyUI。你需要自行配置 SSH、Tailscale SSH 或其它远程启动脚本。

## 调试

调试项默认关闭。只有排查问题时再打开：

- `debug_prompt_enabled`
- `debug_image_reference_enabled`
- `debug_send_payload_enabled`

开启后可能在日志和 `last_task.json` 中记录较长提示词，请注意隐私。

## 推荐做法

普通使用：

1. 先在 WebUI 里只改常用项。
2. 需要更细的控制时，再展开“更多配置”。

深度自定义：

1. 先打开带注释模板。
2. 对照修改真实运行文件 `data/config/astrbot_plugin_anima_master_config.json`。
3. 保存后重载插件。
