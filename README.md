# Anima 绘图大师

一个 **AstrBot** 插件，把聊天里的自然语言变成适合 **本地 ComfyUI / Anima 工作流** 的 Danbooru tags，并把生成结果发回聊天。它把「中文描述 → 提示词优化 → ComfyUI 出图 → 发回群里」整条链路做成一个 `/anm` 指令。

```text
/anm 一个女孩，白色裙子，立绘，简单背景
```

---

## 功能特性

- **文生图**：自然语言自动优化为 Danbooru tags，交由本地 ComfyUI 工作流出图。
- **多人画面**：`/anm 多人` 生成 2–4 人画面，逐人拆解身份、外观、服装、表情、动作与道具，并补全位置与互动关系。
- **标签直出**：`/anm 无优化` 跳过提示词优化，完全按你写的标签直接出图。
- **固定角色**：保存角色名到 tags，指令中命中名字时自动引用；未点名不会自动套用。
- **画师组与画风**：独立保存并切换画师组（`artist:` 串）与画风组，也支持「不使用默认画风」。
- **联网校正角色 Tag**：少量联网搜索补充角色外观/服装参考，再用 Danbooru / Safebooru 角色分类校正，稳定外观锚点。
- **图片法术解析**：读取图片内嵌的生成信息（Prompt / 参数）。
- **视觉模型反推**：根据图片内容反推 Danbooru tags。
- **图片参考**：引用或直接发图后，可在生图描述里写「参考这张图」「同款衣服」等。
- **千代预设**：一键应用 `千代base` / `千代aesthetic` / `千代turbo` 三套画师、模型与参数组合。
- **由 AstrBot 启动 ComfyUI**：ComfyUI 离线且收到绘图请求时，可用 `startup_command` 尝试拉起。
- **0.8.0 背景策略**：自然语言生图在未指定场景时，单人与多人优化路径默认采用 `simple background, white background` 的居中立绘构图；明确指定背景时保留原场景。直出模式与图生图不受这个规则影响。

> 图生图、放大、去背景仍在开发中，默认关闭，不作为稳定主功能。

---

## 工作原理

1. 用户发送 `/anm <描述>`。自然语言描述交给聊天模型（`prompt_builder_provider_id`，留空用会话主模型）。
2. 模型把它整理成 Danbooru tags；固定角色、画师组、画风、质量词与负面词由插件在最终 Prompt 前后拼接。
3. 命中现有作品角色时，先给罗马字角色 tag 候选，再用 Danbooru / Safebooru 角色分类校正；`multi_person` 会额外做一次图片结构校验。
4. 插件把最终 Prompt、尺寸、Steps、CFG 等送入 ComfyUI `/prompt`，轮询生成结果，校验后把图片发回聊天。
5. 生成失败可重试；提示词优化或角色校正不可用时自动降级，不会中断出图。

---

## 安装与前置要求

### 前置要求

- [AstrBot](https://github.com/AstrBotDevs/AstrBot)（`aiocqhttp` 等平台）
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)，以及 Anima 模型、文本编码器（CLIP）和 VAE
- 一个 AstrBot 能访问到的 ComfyUI 地址
- （可选）联网搜索：AstrBot 全局配置里的 Tavily key
- （可选）图片反推：AstrBot 中一个可识图的模型

### 最低启动清单

在插件配置页确认这几项即可出图：

```text
comfyui_base_url = http://127.0.0.1:8188
workflow = anima_t2i
unet_name = 你的 Anima 模型文件名
clip_name = 你的文本编码器文件名
vae_name = 你的 VAE 文件名
```

`127.0.0.1` 指的是 AstrBot 所在机器。如果 AstrBot 和 ComfyUI 不在同一台设备，请填 AstrBot 能访问到的局域网或 Tailscale 地址。

模型文件名必须和 ComfyUI 下拉框里的文件名完全一致，只填文件名，不填本机路径。

多数用户可以先手动启动 ComfyUI（绘世启动器、ComfyUI portable 或自己的脚本）。只有开启「由 AstrBot 启动 ComfyUI」时才需要填 `startup_command`；不开这个功能，不需要启动命令。

### 安装依赖

```bash
pip install -r requirements.txt
```

依赖：`requests`、`pillow`。AstrBot 插件管理器通常会自动处理；若未安装，请手动安装。

---

## 指令列表

`anm` 可以写成 `/anm`、`/anima` 或 `/comfyui`。

| 指令 | 说明 |
|---|---|
| `/anm 生图 <描述>` | 自然语言生图（也支持省略「生图」直接 `/anm <描述>`） |
| `/anm 多人 <描述>` | 生成 2–4 人画面，按人物分组与互动关系构图 |
| `/anm 无优化 <tags>` | 跳过 LLM 优化，直接按你给的标签出图（别名 `/anm 原样`） |
| `/anm 改图 <要求>` | 引用图片后整图重绘 / 风格化（需开启 `img2img_enabled`） |
| `/anm 解析法术` | 读取图片内嵌的生成信息（提示词 / 参数） |
| `/anm 反推` | 根据图片内容反推 Danbooru tags |
| `/anm 状态` | 查看 ComfyUI / Anima 状态 |
| `/anm 诊断` | 检查服务器、网络和 ComfyUI 连接 |
| `/anm 调试状态` | 查看插件关键配置与上次任务摘要 |
| `/anm 添加角色 <名称>=<tags>` | 新增或覆盖固定角色 |
| `/anm 创建画师组 <名称>=<tags>` | 保存并启用画师组 |
| `/anm 追加画师组 <名称>=<tags>` | 追加画师组内容 |
| `/anm 切换画师组 <名称>` | 切换当前画师组 |
| `/anm 查看画师组` | 列出画师组 |
| `/anm 删除画师组 <名称>` | 删除画师组 |
| `/anm 帮助` | 查看指令表 |

> `放大`、`抠图`、`去背景` 仍为开发中能力，默认返回「暂不可用」。

### 每次指定尺寸

每次生图可以单独指定尺寸，不会修改插件默认值：

- 尺寸词：`竖图` / `横图` / `方图`（正方形）/ `长竖图`（手机竖屏）/ `宽屏`（超宽图），插件从当前「可用尺寸列表」里选比例最接近的一项。
- 明写尺寸：`1024x1536：描述`，或在描述末尾加 `--尺寸 1216x832`。
- 明确尺寸不在可用列表时，插件会列出可选尺寸，不会静默替换。

```text
/anm 生图 竖图：狐莉站在梨花树下
/anm 生图 少女站在河岸 --尺寸 1216x832
```

---

## 配置

配置页按使用频率分组，较少使用的项目收进「更多配置」。首次使用先看「ComfyUI 连接」和「出图参数」。

### ComfyUI 连接

| 参数 | 说明 |
|---|---|
| `comfyui_base_url` | AstrBot 能访问到的 ComfyUI 地址，默认 `http://127.0.0.1:8188` |
| `workflow` | 工作流预设，默认 `anima_t2i` |
| `custom_workflow_enabled` | 是否改用自定义 ComfyUI API 工作流（默认关闭） |
| `custom_workflow_path` | 自定义工作流 JSON 路径；千代turbo 自动使用 `variants/turbo/` |
| `timeout` | 等待生成完成的最长时间 |
| `storage_retention_days` | 输入 / 输出图片与任务状态文件的保留天数（`0` 关闭按时间清理） |
| `manifest_max_records` | 输入图片清单压缩后保留的最大有效记录数，默认 `5000` |
| `poll_interval` | 查询 ComfyUI 生成状态的间隔 |
| `auto_start` | ComfyUI 离线且收到绘图请求时尝试启动（不是开机自启） |
| `startup_command` | 开启 `auto_start` 时必填，须能直接启动 ComfyUI 服务 |

### 出图参数

| 参数 | 说明 |
|---|---|
| `width` / `height` | 默认尺寸（会与 `allowed_sizes` 一起生效） |
| `allowed_sizes` | 允许的尺寸列表 |
| `steps` | 采样步数 |
| `cfg` | CFG 强度 |
| `sampler_name` / `scheduler` | 采样器与调度器 |
| `unet_name` / `clip_name` / `vae_name` | 模型文件名（与 ComfyUI 下拉框一致） |
| `quality_prefix` | 固定拼接在正面提示词前的质量词 |
| `negative_prompt` | 默认负面提示词 |

### 自然语言优化

| 参数 | 说明 |
|---|---|
| `prompt_optimize_enabled` | 是否让聊天模型优化自然语言提示词 |
| `prompt_builder_provider_id` | 优化模型 Provider ID；留空用会话主模型 |
| `prompt_builder_max_tokens` | 优化模型最大输出长度 |
| `prompt_builder_max_content_tags` | LLM 内容段硬上限，默认 `65`（不含质量词、固定角色、画师组、画风） |
| `prompt_builder_web_search_enabled` | 允许在需要时联网搜索（需 Tavily key） |
| `prompt_builder_deep_thinking_enabled` | 是否启用深度思考 |
| `prompt_builder_template` | 主提示词模板（一般无需改） |

### 角色与画风

| 参数 | 说明 |
|---|---|
| `fixed_characters` | 固定角色预设，格式 `角色名=tags` |
| `artist_presets` / `active_artist_preset` | 画师组列表与当前启用项 |
| `default_artist_tags` | 未启用画师组时的备用画师 tags |
| `style_presets` / `active_style_preset` / `style_tags` | 画风组与当前画风 |
| `sensual_mode_enabled` | 涩气表现力优化 |
| `sensual_mode_markers` | 触发涩气表现力优化的关键词 |

### 多人生成

| 参数 | 说明 |
|---|---|
| `multi_candidate_count` | 候选采样张数 |
| `multi_verify_enabled` | 是否做图片结构校验 |
| `multi_verify_provider_id` | 图片校验模型 |
| `multi_send_degraded_candidate` | 校验未通过时是否发送最接近的一张 |
| `multi_max_concurrent_generations` | 多人并发上限 |

### 发送与权限

| 参数 | 说明 |
|---|---|
| `send_result_to_chat` | 是否把图片发回聊天 |
| `max_send_images` | 最多发送几张 |
| `admin_only` | 是否仅管理员可用 |
| `allowed_sender_ids` | 允许使用的用户 ID 列表 |

### 其它

- `reset_to_defaults`：一键恢复默认配置（保存后在下一次插件加载时执行一次，随后自动关闭）。
- `chiyo_preset`：选择千代预设（见下）。
- 调试项：`debug_prompt_enabled` / `debug_image_reference_enabled` / `debug_send_payload_enabled`，仅排查问题时临时开启，注意日志及 `last_task.json` 可能记录较长提示词。

> 深度自定义可对照 `docs/advanced-config.example.jsonc`，或本机注释模板 `data/config/astrbot_plugin_anima_master_config.example.jsonc`。真正生效的运行文件是 `data/config/astrbot_plugin_anima_master_config.json`（标准 JSON，不能写注释）。

---

## 提示词与角色画风

### 自然语言生图

普通 `/anm` 会让聊天模型把简短短语自由发展成统一、完整的角色画面，并按主题补充服装、姿态、构图、背景、光影和特效。角色身份、人数、用户明确指定的主体、关键服装、动作、表情和道具仍是核心约束。

```text
/anm 一个女孩，白色裙子，立绘，简单背景
```

### 固定角色

在 `fixed_characters` 中保存角色：

```text
狐莉=1 girl, solo, fox girl, white hair, heterochromia, fang, black choker
```

之后在指令中明确提到角色名时才会拼接该角色 tags；没点名不会自动套用。已保存角色的固定 Tag 是外观身份的唯一依据，即使 LLM 规划了冲突的发色、瞳色或种族特征，插件也会丢弃冲突外观，只保留可变部分。

### 画师与画风

启用画师组后，先拼接当前画师组 tags，再拼当前画风组（用于媒介、上色、渲染）。`default_artist_tags` 仅在未启用画师组时作为备用。某次不想用画师 tags，可在指令里写：

```text
不使用默认画风
no artist tags
```

### 现成 tags

普通 `/anm` 会把现成 Tag 串也交给 LLM 重新设计。需要完全保留时用 `/anm 无优化`：

```text
/anm 无优化 masterpiece, best quality, 1girl, solo, white dress, simple background
```

`无优化` 完全按你给的提示词出图，不拼接质量词、固定角色、画师组或画风，也不清理标签。

### 图片参考与法术

引用或直接发图后：

```text
/anm 解析法术
/anm 反推这张图的提示词
```

也可以在生图请求里写「参考这张图」「图中衣服」「同款衣服」等，让插件把图片内容作为参考。

---

## 千代预设

在「千代预设」中选择 `千代base`、`千代aesthetic` 或 `千代turbo`，会写入对应的千代画师组并把「狐莉」加入固定角色（狐莉不是默认角色，只有点名才用）。

| 预设 | UNet | CFG | 质量词 / 负面词 |
|---|---|---|---|
| 千代base | `anima_baseV10` | 5 | 使用当前配置 |
| 千代aesthetic | `anima_aestheticV11` | 3 | 都不注入 |
| 千代turbo | `anima_baseV10` + `anima-turbo-lora-v0.2` | 1 | 使用当前配置 |

千代turbo 使用 `variants/turbo/workflows/comfyui_00051_api.json`，固定 10 步、`euler`、`simple`，并启用面向 CFG 1 的二次约束规划。选择「未启用」会恢复启用前的值。

---

## 常见问题

### `/anm` 没反应

先确认 AstrBot 是否收到消息。若日志没有新消息，通常是聊天平台适配器或 NapCat / OneBot 连接问题，不是插件问题。

### 提示 ComfyUI 离线

确认 `comfyui_base_url` 是 AstrBot 能访问到的地址。AstrBot 在服务器时，`127.0.0.1` 指服务器自身。可在聊天中发 `/anm 状态`。

### 图片没有发回聊天

确认 `send_result_to_chat=true`、ComfyUI 已生图、平台适配器允许发图。若日志显示生成成功但发送失败，优先检查 OneBot / 平台适配器。

### 参考图拿不到

直接带图发送，或引用一条含图片的消息后再 `/anm`。若提示「检测到图片但没成功下载/保存」说明平台没返回可用图片数据，可稍后重试或改用引用图片。

### 新角色画不像

本地模型不一定认识新角色或冷门角色。可开启联网搜索补充更具体的外观、服装、配色和标志物，或在 `fixed_characters` 中手动添加角色 tags。

### 法术解析读不到提示词

只有部分图片会保留生成信息。经过 QQ、微信、网页或截图转码后信息可能丢失；PNG 原图更容易解析。

### 联网搜索没有生效

联网搜索需要 AstrBot 全局 Tavily key。搜索失败会自动降级，不会中断生图。

---

## 版本变体

插件默认使用内置 `anima_t2i` 工作流、30 步、CFG 5。`variants/` 保存可选版本变体，只有选择对应预设时才加载，详见 [variants/README.md](variants/README.md)。

---

## 开发与测试

```bash
uv run pytest -q
uv run ruff format .
uv run ruff check .
```

---

## License

[MIT](LICENSE) © 2026 YayiMiko

本插件为个人创作工具，图片由本地 ComfyUI / Anima 工作流生成，请确保你拥有合法的模型与素材使用权限，并遵守平台与法律法规。
