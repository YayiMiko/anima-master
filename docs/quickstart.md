# 安装与快速开始

## 前置要求

你需要先准备：

- AstrBot。
- ComfyUI。
- Anima 所需模型、文本编码器和 VAE。
- 一个可以正常访问 ComfyUI 的地址。

如果要使用联网搜索，需要在 AstrBot 全局配置里填写 Tavily key。

如果要使用图片反推，需要在 AstrBot 中配置可识图的模型。

## 最小配置

在 AstrBot WebUI 的插件配置页里，先确认：

```text
enabled = true
comfyui_base_url = http://127.0.0.1:8188
workflow = anima_t2i
unet_name = 你的 Anima 模型文件名
clip_name = 你的文本编码器文件名
vae_name = 你的 VAE 文件名
```

模型文件名必须和 ComfyUI 下拉框中的文件名一致，只填文件名，不填本机路径。

## 第一次测试

在聊天中发送：

```text
/anm 一个女孩，白色裙子，立绘，简单背景
```

如果你已经写好了完整 tags，可以发送：

```text
/anm 原样 masterpiece, best quality, 1girl, solo, white dress, simple background
```

## 尺寸配置

`width` 和 `height` 会和 `allowed_sizes` 一起生效。

推荐用英文半角 `x`：

```text
1024x1536
```

如果 `width` 和 `height` 不在 `allowed_sizes` 中，插件会自动选择最接近的允许尺寸。
