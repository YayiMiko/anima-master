# Turbo 变体

这里保存当前未启用的 Anima Turbo 方案。普通版不会自动读取本目录。

## 与普通版的主要差异

- 加载 `anima-turbo-lora-v0.2.safetensors`。
- 采样参数为 10 步、CFG 1、`euler`、`simple`。
- 使用自定义 ComfyUI API 工作流，并保留工作流内部参数。
- 可配合 `low_cfg_harness/` 中的二次 LLM 约束、优先 Tag、冲突删除、画风加权和动态截断逻辑。

## 留档内容

- `workflows/comfyui_00051_api.json`：Turbo API 工作流原件。
- `low_cfg_harness/`：从普通版拆除的低 CFG 提示词约束原件。
- `config.example.jsonc`：Turbo 相关配置示例。

## 恢复注意事项

工作流要求 ComfyUI 能找到对应的基础模型、CLIP、VAE 和 Turbo LoRA。只启用工作流不会自动恢复低 CFG harness；如需恢复 harness，应整体核对三份 Python 原件、提示词模板、配置结构和测试，不能只复制单个文件。
