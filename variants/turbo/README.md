# Turbo 变体

这里保存千代turbo 预设使用的 Anima Turbo 工作流与低 CFG 约束方案。其他预设不会读取本目录。

## 与普通版的主要差异

- 加载 `anima-turbo-lora-v0.2.safetensors`。
- 采样参数为 10 步、CFG 1、`euler`、`simple`。
- 使用自定义 ComfyUI API 工作流，并保留工作流内部参数。
- 千代turbo 会启用二次 LLM 约束、优先 Tag、冲突删除、画风加权和动态截断逻辑。

## 留档内容

- `workflows/comfyui_00051_api.json`：Turbo API 工作流原件。
- `low_cfg_harness/`：低 CFG 提示词约束的留档原件；当前运行代码位于插件根目录。
- `config.example.jsonc`：Turbo 相关配置示例。

## 恢复注意事项

工作流要求 ComfyUI 能找到对应的基础模型、CLIP、VAE 和 Turbo LoRA。选择千代turbo 后会同时启用工作流和当前版本的低 CFG harness。修改留档原件不会直接改变运行行为；调整时应同步核对提示词模板、配置结构和测试。
