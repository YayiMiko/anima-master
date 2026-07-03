import json
from pathlib import Path
from typing import Any

try:
    from .prompt_presets import apply_config_preset, fixed_character_tags
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from prompt_presets import apply_config_preset, fixed_character_tags


def _bool(config: dict[str, Any], key: str, default: bool) -> bool:
    return bool(config.get(key, default))


def _int(config: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(config.get(key, default))
    except (TypeError, ValueError):
        return default


def _str(config: dict[str, Any], key: str, default: str = "") -> str:
    value = config.get(key, default)
    return str(value if value is not None else default)


class TaskRecorder:
    """Persist and render non-secret Anima task state."""

    def __init__(self, path: Path, logger: Any):
        """Create a task recorder.

        Args:
            path: Destination path for the latest task JSON.
            logger: Logger-like object used for warning messages.
        """
        self.path = Path(path)
        self._logger = logger

    def write(self, task: dict[str, Any]) -> None:
        """Persist a non-secret summary for the latest Anima task.

        Args:
            task: Summary fields for the task. Values must avoid API keys,
                cookies, account tokens, and other secrets.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(task, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self._logger.warning("[comfyui_agent] failed to write last task summary: %s", exc)

    def read(self) -> dict[str, Any]:
        """Read the latest non-secret Anima task summary.

        Returns:
            The latest task summary, or an empty dict when the file is missing
            or unreadable.
        """
        try:
            if not self.path.exists():
                return {}
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            self._logger.warning("[comfyui_agent] failed to read last task summary: %s", exc)
            return {}

    def debug_status_text(self, config: dict[str, Any]) -> str:
        """Build a non-secret debug summary for chat-side inspection.

        Args:
            config: Current plugin configuration.

        Returns:
            A compact text summary of key Anima plugin settings and the latest
            task record path.
        """
        prompt_config = apply_config_preset(dict(config or {}))
        characters = sorted(fixed_character_tags(prompt_config).keys())
        last_task = self.read()
        prompt_template = _str(config, "prompt_builder_template", "").strip()
        lines = [
            "Anima 调试状态：",
            f"- 提示词优化：{_bool(config, 'prompt_optimize_enabled', True)}",
            f"- 自定义 Prompt 模板：{bool(prompt_template)}",
            f"- 提示词生成风格：{_str(config, 'prompt_builder_style', '') or '默认'}",
            f"- 默认画风：{_bool(config, 'default_style_enabled', False)} / {_str(config, 'default_style_name', '') or '未命名'}",
            f"- 固定角色：{', '.join(characters) if characters else '无'}",
            f"- 联网搜索：{_bool(config, 'prompt_builder_web_search_enabled', True)}",
            f"- 深度思考：{_bool(config, 'prompt_builder_deep_thinking_enabled', True)} / {_str(config, 'prompt_builder_reasoning_effort', 'max')}",
            f"- Danbooru 核心 tag 查询：{_bool(config, 'danbooru_core_tag_lookup_enabled', True)}",
            f"- 图生图：{_bool(config, 'img2img_enabled', False)}",
            f"- 发送到聊天：{_bool(config, 'send_result_to_chat', True)} / 最多 {_int(config, 'max_send_images', 1)} 张",
            f"- ComfyUI：{_str(config, 'comfyui_base_url', 'http://127.0.0.1:8188')}",
            f"- 工作流：{_str(config, 'workflow', 'anima_t2i')}",
            f"- 默认尺寸：{_int(config, 'width', 832)}x{_int(config, 'height', 1216)}",
            f"- 模型：UNET={_str(config, 'unet_name', '') or '未配置'}，CLIP={_str(config, 'clip_name', '') or '未配置'}，VAE={_str(config, 'vae_name', '') or '未配置'}",
            f"- 调试开关：prompt={_bool(config, 'debug_prompt_enabled', False)}，reference={_bool(config, 'debug_image_reference_enabled', False)}，send={_bool(config, 'debug_send_payload_enabled', False)}",
            f"- 上次任务：{self.path if self.path.exists() else '暂无'}",
        ]
        if last_task:
            prompt_summary = last_task.get("prompt_summary")
            if not isinstance(prompt_summary, dict):
                prompt_summary = {}
            lines.extend(
                [
                    "",
                    "上次任务摘要：",
                    f"- 时间：{last_task.get('time') or '未知'}",
                    f"- 动作：{last_task.get('action') or '未知'} / 成功：{last_task.get('ok')}",
                    f"- 错误：{last_task.get('error') or '无'}",
                    f"- 引用图：requested={last_task.get('reference_image_requested')} applied={last_task.get('reference_context_applied')}",
                    f"- 固定角色：{prompt_summary.get('fixed_character_name') or '无'}",
                    f"- 搜索/思考：{prompt_summary.get('web_search')} / {prompt_summary.get('deep_thinking')}",
                    f"- 最终 prompt 长度：{prompt_summary.get('final_prompt_chars') or 0}",
                    f"- 输出：{len(last_task.get('outputs') or [])} 张",
                ]
            )
        return "\n".join(lines)
