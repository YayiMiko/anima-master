# 配置说明

配置页按使用频率分组。首次使用时，只需要先看前四组。

## 基础

- `enabled`：是否启用插件。
- `preset_profile`：一键预设。可选 `none` 或 `chiyo`。

`chiyo` 会启用一套可直接体验的默认配置，包括千代画风、Anima 常用参数和狐莉固定角色。狐莉不是默认角色，只有指令里明确提到“狐莉”时才会使用。

## ComfyUI

- `comfyui_base_url`：AstrBot 能访问到的 ComfyUI 地址。
- `workflow`：工作流预设，目前公开版内置 `anima_t2i`。
- `timeout`：等待生成完成的最长时间。
- `poll_interval`：查询 ComfyUI 生成状态的间隔。

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
- `prompt_builder_max_content_tags`：具体内容 tags 数量上限。
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
- `default_style_enabled`：默认拼接画风或画师 tags。
- `default_style_name`：画风名称。
- `default_artist_tags`：画师 tags。
- `sensual_mode_enabled`：边界表现力模式。
- `sensual_mode_markers`：触发表现力模式的关键词。

固定角色格式：

```text
角色名=danbooru tags
```

## 开发中旁路

图生图、放大和去背景仍在开发中。配置项保留给后续版本使用，不建议作为稳定功能依赖。

## 发送与权限

- `send_result_to_chat`：是否把图片发回聊天。
- `max_send_images`：最多发送几张。
- `admin_only`：是否仅管理员可用。
- `allowed_sender_ids`：允许使用的用户 ID 列表。

## 自动启动

`auto_start` 会在 AstrBot 所在机器上执行 `startup_command`。

如果 ComfyUI 在另一台机器，自动启动不会直接启动远端 ComfyUI。你需要自行配置 SSH、Tailscale SSH 或其它远程启动脚本。

## 调试

调试项默认关闭。只有排查问题时再打开：

- `debug_prompt_enabled`
- `debug_image_reference_enabled`
- `debug_send_payload_enabled`

开启后可能在日志和 `last_task.json` 中记录较长提示词，请注意隐私。
