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
- `chiyo_preset`：选择千代预设。可选 `未启用` / `千代base` / `千代aesthetic`（配置值分别为空、`base`、`aesthetic`）。

未启用时使用当前配置。选择任一千代预设后，都会把千代画师组写入画师 tags，并把狐莉加入固定角色。狐莉不是默认角色，只有指令里明确提到“狐莉”时才会使用。

各预设差异：

| 预设 | UNet | CFG | 质量词 / 负面词 |
| --- | --- | --- | --- |
| 千代base | `anima_baseV10.safetensors` | 5 | 使用当前配置的质量词与负面词 |
| 千代aesthetic | `anima_aestheticV11.safetensors` | 3 | 都不注入 |

`steps`、`sampler_name`、`scheduler`、CLIP 与 VAE 两个预设一致。预设只在运行时覆盖对应配置项，不会破坏原有基础配置；选择“未启用”后会恢复原值。切换后需保存配置并重载插件。旧配置里的 `chiyo_preset_enabled` 与旧画师组名“千代风格”“千代画风”仍可识别，并会迁移到千代base。

## ComfyUI 连接

- `comfyui_base_url`：AstrBot 能访问到的 ComfyUI 地址。
- `workflow`：工作流预设，默认使用 `anima_t2i`。
- `custom_workflow_enabled`：是否改用自定义 ComfyUI API 工作流；普通版默认关闭。
- `custom_workflow_path`：自定义工作流 JSON 路径；Turbo 留档示例见 `variants/turbo/`。
- `timeout`：等待生成完成的最长时间。
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
- `prompt_builder_max_content_tags`：LLM 内容段的 Tag 上限，默认 80；不计算质量词、固定角色、画师组和画风。
- `prompt_builder_template`：主提示词模板。

通常不需要一开始就改 `prompt_builder_template`。如果想改变插件如何理解中文需求，再调整它。

## 联网与 tag 查询

- `prompt_builder_web_search_enabled`：允许在需要时联网搜索。
- `prompt_builder_search_query_template`：搜索查询模板。
- `danbooru_core_tag_lookup_enabled`：校正少量疑似角色核心 tag。
- `danbooru_tag_base_urls`：Donmai tag API 地址。

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
