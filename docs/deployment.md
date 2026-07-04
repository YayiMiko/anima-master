# 部署拓扑

## AstrBot 和 ComfyUI 在同一台机器

这是最简单的部署方式。

```text
comfyui_base_url = http://127.0.0.1:8188
```

## AstrBot 在服务器，ComfyUI 在另一台机器

这种情况下，`127.0.0.1` 指服务器自身，不是家里电脑。

请填写服务器能访问到的 ComfyUI 地址：

```text
comfyui_base_url = http://100.x.x.x:8188
```

如果使用 Tailscale，可以填写 ComfyUI 所在机器的 Tailscale IP。

ComfyUI 需要允许外部访问。常见启动参数：

```text
--listen 0.0.0.0
```

同时确认防火墙、路由和 Tailscale ACL 没有阻断 8188 端口。

## AstrBot 在本机，NapCat 在服务器

这种部署可以使用。

插件生成图片后，会由 AstrBot 平台适配器发送图片组件，不要求服务器 NapCat 读取本机磁盘路径。

如果图片发送失败，请优先检查：

- AstrBot 是否成功生成了图片文件。
- OneBot 连接是否正常。
- 平台适配器是否允许发送图片。

不要把本机 `D:\...` 路径配置给服务器 NapCat。

## 自动启动 ComfyUI

`auto_start` 只会在 AstrBot 所在机器执行命令。

如果 AstrBot 和 ComfyUI 不在同一台机器，跨机器自动启动需要自行配置远程命令。
