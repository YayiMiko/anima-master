import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

try:
    from .prompt_presets import (
        active_artist_preset_name,
        active_artist_tags,
        apply_config_preset,
        artist_presets,
        chiyo_profile_display_name,
        fixed_character_tags,
    )
    from .task_summary import build_last_task_debug_lines, build_strategy_summary
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from prompt_presets import (
        active_artist_preset_name,
        active_artist_tags,
        apply_config_preset,
        artist_presets,
        chiyo_profile_display_name,
        fixed_character_tags,
    )
    from task_summary import build_last_task_debug_lines, build_strategy_summary


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
        self._lock = threading.RLock()
        self._tasks_dir = self.path.parent / "tasks"

    def write(self, task: dict[str, Any]) -> None:
        """Persist a non-secret summary for the latest Anima task.

        Args:
            task: Summary fields for the task. Values must avoid API keys,
                cookies, account tokens, and other secrets.
        """
        try:
            task_id = str(task.get("task_id") or "").strip()
            if not task_id:
                raise ValueError("task_id is required")
            payload = json.dumps(task, ensure_ascii=False, indent=2)
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._tasks_dir.mkdir(parents=True, exist_ok=True)
                task_path = self._tasks_dir / f"{task_id}.json"
                task_existed = task_path.exists()
                task_temp = task_path.with_name(
                    f".{task_path.name}.{uuid.uuid4().hex}.tmp"
                )
                task_temp.write_text(payload, encoding="utf-8")
                os.replace(task_temp, task_path)

                latest = self.read()
                if not latest or latest.get("task_id") in {None, task_id}:
                    latest_temp = self.path.with_name(
                        f".{self.path.name}.{uuid.uuid4().hex}.tmp"
                    )
                    latest_temp.write_text(payload, encoding="utf-8")
                    os.replace(latest_temp, self.path)
                elif not task_existed and str(task.get("time") or "") >= str(
                    latest.get("time") or ""
                ):
                    latest_temp = self.path.with_name(
                        f".{self.path.name}.{uuid.uuid4().hex}.tmp"
                    )
                    latest_temp.write_text(payload, encoding="utf-8")
                    os.replace(latest_temp, self.path)
        except Exception as exc:
            self._logger.warning(
                "[comfyui_agent] failed to write last task summary: %s", exc
            )

    def read(self, task_id: str | None = None) -> dict[str, Any]:
        """Read the latest non-secret Anima task summary.

        Returns:
            The latest task summary, or an empty dict when the file is missing
            or unreadable.
        """
        try:
            path = self._tasks_dir / f"{task_id}.json" if task_id else self.path
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            self._logger.warning(
                "[comfyui_agent] failed to read last task summary: %s", exc
            )
            return {}

    def build_generation_start(
        self,
        *,
        event: Any,
        started_at: Any,
        original_prompt: str,
        reference_requested: bool,
        width: int,
        height: int,
        explicit_size: bool,
        steps: int,
        cfg: float,
        workflow: str,
        shorten: Any,
    ) -> dict[str, Any]:
        """Build the initial standard task record for a generation request.

        Args:
            event: AstrBot message event.
            started_at: Datetime-like task start value.
            original_prompt: User prompt before reference augmentation.
            reference_requested: Whether the prompt requested an image reference.
            width: Effective requested width.
            height: Effective requested height.
            explicit_size: Whether chat or an LLM tool explicitly requested the size.
            steps: Effective requested step count.
            cfg: Effective requested CFG value.
            workflow: Configured workflow type.
            shorten: Text shortening callable.

        Returns:
            A non-secret task record with legacy and standard fields.
        """
        prompt_head = shorten(original_prompt, 1000)
        return {
            "task_id": uuid.uuid4().hex,
            "time": started_at.isoformat(timespec="microseconds"),
            "action": "generate",
            "platform_id": event.get_platform_id(),
            "session_id": event.get_session_id(),
            "sender_id": event.get_sender_id(),
            "ok": None,
            "error": "",
            "workflow": workflow,
            "size": {"width": width, "height": height},
            "requested_size": {
                "width": width,
                "height": height,
                "explicit": explicit_size,
            },
            "actual_size": None,
            "parameters": {"steps": steps, "cfg": cfg},
            "reference": {
                "requested": reference_requested,
                "image_found": None,
                "context_applied": False,
            },
            "image_input": {},
            "prompt": {
                "original_head": prompt_head,
                "summary": {},
            },
            "outputs": [],
            "elapsed_seconds": None,
            # Legacy fields kept for existing debug/diagnostic readers.
            "original_prompt": prompt_head,
            "reference_image_requested": reference_requested,
            "reference_context_applied": False,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
        }

    def mark_failure(self, task: dict[str, Any], error: str) -> None:
        """Mark a task as failed.

        Args:
            task: Mutable task record.
            error: Stable error code or short reason.
        """
        task["ok"] = False
        task["error"] = error

    def mark_reference_missing(
        self,
        task: dict[str, Any],
        image_input_summary: dict[str, Any],
    ) -> None:
        """Mark a task as failed because no requested reference image was found.

        Args:
            task: Mutable task record.
            image_input_summary: Latest image input resolver summary.
        """
        self.mark_failure(task, "reference_image_not_found")
        task["reference_image_found"] = False
        task["image_input_summary"] = image_input_summary
        task["image_input"] = dict(image_input_summary)
        if isinstance(task.get("reference"), dict):
            task["reference"]["image_found"] = False

    def mark_reference_context(
        self,
        task: dict[str, Any],
        *,
        image_input_summary: dict[str, Any],
        reference_context_summary: dict[str, Any],
        applied: bool,
    ) -> None:
        """Record reference image and context summaries.

        Args:
            task: Mutable task record.
            image_input_summary: Image input resolver summary.
            reference_context_summary: Reference context summary.
            applied: Whether reference context changed the prompt.
        """
        task["image_input_summary"] = image_input_summary
        task["reference_context_summary"] = reference_context_summary
        task["reference_context_applied"] = applied
        task["image_input"] = dict(image_input_summary)
        if isinstance(task.get("reference"), dict):
            task["reference"]["image_found"] = bool(image_input_summary.get("path"))
            task["reference"]["context_applied"] = applied
            task["reference"]["context"] = dict(reference_context_summary)

    def mark_prompt_built(
        self, task: dict[str, Any], prompt_summary: dict[str, Any]
    ) -> None:
        """Record prompt build summary on a task.

        Args:
            task: Mutable task record.
            prompt_summary: Non-secret prompt pipeline summary.
        """
        prompt_summary = dict(prompt_summary)
        prompt_summary["llm_ok"] = not bool(prompt_summary.get("llm_failed"))
        if "stage_events" not in prompt_summary:
            prompt_summary["stage_events"] = [
                {
                    "stage": "prompt_llm",
                    "status": (
                        "failed"
                        if prompt_summary.get("llm_failed")
                        else prompt_summary.get("skipped_reason") or "ok"
                    ),
                }
            ]
        task["prompt_summary"] = prompt_summary
        task["strategy_summary"] = build_strategy_summary(task, prompt_summary)
        if isinstance(task.get("prompt"), dict):
            task["prompt"]["summary"] = dict(prompt_summary)

    def mark_completed(
        self,
        task: dict[str, Any],
        *,
        payload: dict[str, Any],
        elapsed_seconds: float,
        include_payload: bool = False,
    ) -> None:
        """Record final ComfyUI helper payload summary.

        Args:
            task: Mutable task record.
            payload: ComfyUI helper payload.
            elapsed_seconds: Rounded task duration.
            include_payload: Whether to include the raw helper payload.
        """
        task["ok"] = bool(payload.get("ok"))
        task["error"] = payload.get("error") or ""
        task["outputs"] = payload.get("outputs") or []
        task["elapsed_seconds"] = elapsed_seconds
        if payload.get("width") and payload.get("height"):
            task["actual_size"] = {
                "width": int(payload["width"]),
                "height": int(payload["height"]),
            }
        if include_payload:
            task["tool_payload"] = payload

    def mark_delivery(self, task: dict[str, Any], delivery: dict[str, Any]) -> None:
        """Record chat delivery state after generation output handling.

        Args:
            task: Mutable task record.
            delivery: Delivery state produced by `chat_delivery`.
        """
        task["delivery"] = dict(delivery)

    def debug_status_text(self, config: dict[str, Any]) -> str:
        """Build a non-secret debug summary for chat-side inspection.

        Args:
            config: Current plugin configuration.

        Returns:
            A compact text summary of key Anima plugin settings and the latest
            task record path.
        """
        config = apply_config_preset(dict(config or {}))
        prompt_config = config
        characters = sorted(fixed_character_tags(prompt_config).keys())
        presets = sorted(artist_presets(prompt_config).keys())
        active_artist = active_artist_preset_name(prompt_config)
        last_task = self.read()
        prompt_template = _str(config, "prompt_builder_template", "").strip()
        artist_tags = active_artist_tags(prompt_config).strip()
        lines = [
            "Anima 调试状态：",
            f"- 提示词优化：{_bool(config, 'prompt_optimize_enabled', True)}",
            f"- 自定义 Prompt 模板：{bool(prompt_template)}",
            f"- 千代预设：{chiyo_profile_display_name(config)}",
            f"- 低 CFG 提示词约束：{_bool(config, 'low_cfg_harness_enabled', False)}",
            f"- 画师 tags：{'已配置' if artist_tags else '未配置'}",
            f"- 当前画师组：{active_artist or '默认画师 tags'}",
            f"- 已保存的画师组：{', '.join(presets) if presets else '无'}",
            f"- 角色：{', '.join(characters) if characters else '无'}",
            f"- 联网搜索：{_bool(config, 'prompt_builder_web_search_enabled', True)}",
            f"- 深度思考：{_bool(config, 'prompt_builder_deep_thinking_enabled', True)} / {_str(config, 'prompt_builder_reasoning_effort', 'high')}",
            f"- Danbooru 核心 tag 查询：{_bool(config, 'danbooru_core_tag_lookup_enabled', True)}",
            f"- 图生图：{_bool(config, 'img2img_enabled', False)}",
            f"- 发送到聊天：{_bool(config, 'send_result_to_chat', True)} / 最多 {_int(config, 'max_send_images', 1)} 张",
            f"- ComfyUI：{_str(config, 'comfyui_base_url', 'http://127.0.0.1:8188')}",
            f"- 工作流：{_str(config, 'custom_workflow_path') if _bool(config, 'custom_workflow_enabled', False) else _str(config, 'workflow', 'anima_t2i')}",
            f"- 默认尺寸：{_int(config, 'width', 1024)}x{_int(config, 'height', 1536)}",
            f"- 模型：UNET={_str(config, 'unet_name', '') or '未配置'}，CLIP={_str(config, 'clip_name', '') or '未配置'}，VAE={_str(config, 'vae_name', '') or '未配置'}",
            f"- 调试开关：prompt={_bool(config, 'debug_prompt_enabled', False)}，reference={_bool(config, 'debug_image_reference_enabled', False)}，send={_bool(config, 'debug_send_payload_enabled', False)}",
            f"- 上次任务：{self.path if self.path.exists() else '暂无'}",
        ]
        if last_task:
            lines.extend(["", *build_last_task_debug_lines(last_task)])
        return "\n".join(lines)
