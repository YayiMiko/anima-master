# 项目结构

AstrBot 从插件根目录加载 `main.py`；`metadata.yaml`、`_conf_schema.json` 和 `_conf_sections.json` 也保留在根目录。其余插件逻辑按职责收在 `anima/` 包内。

```text
main.py                  AstrBot 入口与事件注册
anima/commands/          指令目录、路由和执行
anima/prompts/           提示词规划、角色查询、Tag 处理
anima/images/            图片输入、引用和存储
anima/runtime/           ComfyUI 调度、任务状态、发送与诊断
agent_tools/             独立运行的 ComfyUI 辅助脚本
variants/                可选预设与工作流
data/                    插件随附模板，不是运行时数据目录
tests/                   单元与回归测试
```

`main.py` 创建服务容器，指令经 `commands/` 进入提示词与图片处理模块，再由 `runtime/` 调用 `agent_tools/` 里的独立脚本。`agent_tools/` 暂时保留原路径，因为运行时会以子进程执行其中的脚本。插件运行数据写在 AstrBot 的数据目录，不应提交到本仓库。

修改模块位置时，需要同步检查包内导入、`main.py`、`agent_tools/` 的跨包导入、测试，以及部署时旧文件的清理。仅在已有插件目录上覆盖新文件可能留下旧模块，掩盖导入错误；应在干净的插件目录验证。
