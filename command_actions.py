from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from .agent_tools.comfyui_sizes import allowed_sizes
    from .command_catalog import COMMAND_ENTRIES
    from .command_router import (
        DEFAULT_GENERATION_SIZES,
        help_text,
        parse_generation_size,
    )
    from .config_defaults import persist_flat_config_key
    from .deployment_diagnostics import compact_status_text, diagnostic_text
    from .multi_person_prompt import MULTI_PERSON_NEGATIVE_TAGS
    from .prompt_presets import (
        DEFAULT_NEGATIVE_PROMPT,
        active_artist_preset_name,
        artist_presets,
        fixed_character_tags,
        merge_tag_text,
    )
    from .tag_cleaner import canonical_tag_text, join_prompt_parts, split_tags
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from agent_tools.comfyui_sizes import allowed_sizes
    from command_catalog import COMMAND_ENTRIES
    from command_router import (
        DEFAULT_GENERATION_SIZES,
        help_text,
        parse_generation_size,
    )
    from config_defaults import persist_flat_config_key
    from deployment_diagnostics import compact_status_text, diagnostic_text
    from multi_person_prompt import MULTI_PERSON_NEGATIVE_TAGS
    from prompt_presets import (
        DEFAULT_NEGATIVE_PROMPT,
        active_artist_preset_name,
        artist_presets,
        fixed_character_tags,
        merge_tag_text,
    )
    from tag_cleaner import canonical_tag_text, join_prompt_parts, split_tags


SCHEMA_PATH = Path(__file__).with_name("_conf_schema.json")


class CommandActionHandler:
    """Dispatch chat commands to Anima plugin actions."""

    def __init__(
        self,
        *,
        config: dict[str, Any],
        task_recorder: Any,
        reference_context: Any,
        is_allowed: Callable[[Any], bool],
        run_tool: Callable[[list[str]], Any],
        ensure_ready: Callable[[Any], Any],
        send_payload: Callable[[Any, dict[str, Any]], Any],
        generate: Callable[..., Any],
        event_image_input: Callable[[Any], Any],
        build_prompt: Callable[..., Any],
        format_spell_payload: Callable[[dict[str, Any]], str],
        get_bool: Callable[[str, bool], bool],
        shorten: Callable[[str, int], str],
        config_store: Any = None,
        image_input_summary: Callable[[], dict[str, Any]] | None = None,
    ):
        """Store dependencies for command-side action handling.

        Args:
            config: Plugin configuration dict.
            task_recorder: Task recorder used for debug status output.
            reference_context: Reference-context builder for spell/reverse.
            is_allowed: Permission checker.
            run_tool: Main ComfyUI helper runner.
            ensure_ready: ComfyUI readiness checker.
            send_payload: Chat payload sender.
            generate: Text-to-image generator.
            event_image_input: Image input resolver.
            image_input_summary: Latest image input summary callback.
            build_prompt: Prompt builder for img2img.
            format_spell_payload: Spell payload formatter.
            get_bool: Config boolean accessor.
            shorten: Text-shortening helper.
        """
        self.config = config
        self._config_store = config_store
        self._task_recorder = task_recorder
        self._reference_context = reference_context
        self._is_allowed = is_allowed
        self._run_tool = run_tool
        self._ensure_ready = ensure_ready
        self._send_payload = send_payload
        self._generate = generate
        self._event_image_input = event_image_input
        self._image_input_summary = image_input_summary or (lambda: {})
        self._build_prompt = build_prompt
        self._format_spell_payload = format_spell_payload
        self._bool = get_bool
        self._shorten = shorten

    def action_names(self) -> set[str]:
        """Return all command actions understood by this handler."""
        return {entry.action for entry in COMMAND_ENTRIES}

    def _persist_config_key(self, key: str, value: Any) -> None:
        self.config[key] = value
        if isinstance(self._config_store, dict):
            persist_flat_config_key(self._config_store, SCHEMA_PATH, key, value)
        save_config = getattr(self._config_store, "save_config", None)
        if callable(save_config):
            save_config()

    def _normalize_tag_text(self, text: str) -> str:
        tags = [canonical_tag_text(tag) for tag in split_tags(text)]
        normalized = join_prompt_parts([", ".join(tags)])
        return normalized + ("," if normalized else "")

    def _parse_name_tags(self, text: str) -> tuple[str, str] | None:
        raw = str(text or "").strip()
        candidates: list[tuple[int, str]] = []
        for separator in ("=", "＝", "：", ":"):
            index = raw.find(separator)
            if index >= 0:
                candidates.append((index, separator))
        for index, separator in sorted(candidates):
            name = raw[:index].strip()
            tags = raw[index + len(separator) :].strip()
            if not self._is_name_tags_separator(name, tags):
                continue
            tags = self._normalize_tag_text(tags)
            if name and tags:
                return name, tags
        return None

    def _is_name_tags_separator(self, name: str, tags: str) -> bool:
        if not name or not tags:
            return False
        if "," in name or "\n" in name:
            return False
        if re.search(r"[@()[\]{}]", name):
            return False
        lowered = name.strip().lower()
        if lowered in {"artist", "tag", "tags", "prompt", "positive", "negative"}:
            return False
        return True

    def _save_artist_preset(self, name: str, tags: str) -> str:
        presets = artist_presets(self.config)
        presets[name] = tags
        self._persist_artist_presets(presets, active=name)
        return f"已保存并启用画师组“{name}”：\n" + self._shorten(tags, 800)

    def create_artist_preset(self, prompt: str) -> str:
        parsed = self._parse_name_tags(prompt)
        if not parsed:
            return "请使用“名称=tags”的格式。例：/anm 创建画师组 千代风格=@artist_a, @artist_b,"
        name, tags = parsed
        return self._save_artist_preset(name, tags)

    def _persist_artist_presets(
        self, presets: dict[str, str], active: str | None = None
    ) -> None:
        lines = [f"{name}={tags}" for name, tags in presets.items()]
        self._persist_config_key("artist_presets", lines)
        if active is not None:
            self._persist_config_key("active_artist_preset", active)

    def set_artist_tags(self, prompt: str) -> str:
        parsed = self._parse_name_tags(prompt)
        if parsed:
            name, tags = parsed
            return self._save_artist_preset(name, tags)

        tags = self._normalize_tag_text(prompt)
        if not tags:
            return "请写画师 tags，或使用“名称=tags”。例：/anm 创建画师组 千代=@artist_a, @artist_b,"
        self._persist_config_key("default_artist_tags", tags)
        self._persist_config_key("active_artist_preset", "")
        return "已设置默认画师 tags，并切回默认画师 tags：\n" + self._shorten(tags, 800)

    def append_artist_tags(self, prompt: str) -> str:
        parsed = self._parse_name_tags(prompt)
        if parsed:
            name, tags = parsed
            presets = artist_presets(self.config)
            merged = merge_tag_text(presets.get(name), tags)
            presets[name] = merged
            self._persist_artist_presets(presets, active=name)
            return f"已追加并启用画师组“{name}”：\n" + self._shorten(merged, 800)

        addition = self._normalize_tag_text(prompt)
        if not addition:
            return "请写要追加的画师 tags，或使用“名称=tags”。例：/anm 追加画师组 千代=@artist_a,"
        active = active_artist_preset_name(self.config)
        if active:
            presets = artist_presets(self.config)
            merged = merge_tag_text(presets.get(active), addition)
            presets[active] = merged
            self._persist_artist_presets(presets, active=active)
            return f"已追加当前画师组“{active}”：\n" + self._shorten(merged, 800)
        merged = merge_tag_text(self.config.get("default_artist_tags"), addition)
        self._persist_config_key("default_artist_tags", merged)
        return "已追加默认画师 tags：\n" + self._shorten(merged, 800)

    def use_artist_preset(self, prompt: str) -> str:
        name = str(prompt or "").strip()
        if not name:
            return "请写要启用的画师组名称。例：/anm 切换画师组 千代"
        if name in {"默认", "默认画师", "默认画师组", "default"}:
            self._persist_config_key("active_artist_preset", "")
            return "已切回默认画师 tags。"
        presets = artist_presets(self.config)
        if name not in presets:
            return f"没有找到画师组“{name}”。可用画师组：{', '.join(sorted(presets)) if presets else '无'}"
        self._persist_config_key("active_artist_preset", name)
        return f"已启用画师组“{name}”：\n" + self._shorten(presets[name], 800)

    def list_artist_presets(self) -> str:
        presets = artist_presets(self.config)
        active = active_artist_preset_name(self.config)
        default_tags = str(self.config.get("default_artist_tags") or "").strip()
        lines = ["画师组："]
        lines.append(
            f"- 默认画师 tags：{'已配置' if default_tags else '未配置'}{'（当前）' if not active else ''}"
        )
        if not presets:
            lines.append("- 已保存的画师组：无")
        else:
            for name in sorted(presets):
                marker = "（当前）" if name == active else ""
                lines.append(f"- {name}{marker}：{self._shorten(presets[name], 120)}")
        lines.extend(
            [
                "",
                "用法：",
                "/anm 创建画师组 名称=@artist_a, @artist_b,",
                "/anm 切换画师组 名称",
                "/anm 删除画师组 名称",
            ]
        )
        return "\n".join(lines)

    def delete_artist_preset(self, prompt: str) -> str:
        name = str(prompt or "").strip()
        if not name:
            return "请写要删除的画师组名称。例：/anm 删除画师组 千代"
        presets = artist_presets(self.config)
        if name not in presets:
            return f"没有找到画师组“{name}”。"
        presets.pop(name, None)
        active = active_artist_preset_name(self.config)
        self._persist_artist_presets(presets, active="" if active == name else active)
        return f"已删除画师组“{name}”。" + (
            " 当前已切回默认画师 tags。" if active == name else ""
        )

    def add_fixed_character(self, prompt: str) -> str:
        parsed = self._parse_name_tags(prompt)
        if not parsed:
            return (
                "请使用“名称=tags”的格式。例：/anm 添加角色 狐莉=1girl, solo, fox girl,"
            )
        name, tags = parsed
        characters = fixed_character_tags(self.config)
        characters[name] = tags
        lines = [
            f"{character_name}={character_tags}"
            for character_name, character_tags in characters.items()
        ]
        self._persist_config_key("fixed_characters", lines)
        return f"已保存角色“{name}”：\n" + self._shorten(tags, 1000)

    def status_text(self, payload: dict[str, Any]) -> str:
        """Render a chat-visible ComfyUI status response.

        Args:
            payload: Status payload returned by the ComfyUI helper.

        Returns:
            Human-readable status text.
        """
        return compact_status_text(payload)

    def diagnose_text(self, payload: dict[str, Any]) -> str:
        """Render a deployment-focused diagnostic response.

        Args:
            payload: Status payload returned by the ComfyUI helper.

        Returns:
            Human-readable diagnostic text.
        """
        return diagnostic_text(
            payload,
            self.config,
            self._task_recorder.read(),
            self._image_input_summary(),
        )

    async def edit(self, event: Any, prompt: str) -> str:
        if not self._bool("img2img_enabled", False):
            return "图生图/改图功能已关闭。当前先保留文生图、法术解析和图片反推主线。"
        if not self._is_allowed(event):
            return "ComfyUI 助手已关闭，或当前用户没有使用权限。"
        ready = await self._ensure_ready(event)
        if not ready.get("ok"):
            return await self._send_payload(event, ready)
        prompt = str(prompt or "").strip()
        if not prompt:
            return "请在后面写改图提示词。"
        image_input = await self._event_image_input(event)
        if not image_input:
            return "改图失败：请在本次消息中附图，或引用一条包含图片的消息。"
        if self._bool("prompt_optimize_img2img_enabled", False):
            prompt = await self._build_prompt(event, prompt, mode="img2img")
        payload = await self._run_tool(
            ["edit", "--prompt", prompt, "--input", image_input]
        )
        return await self._send_payload(event, payload)

    async def spell(self, event: Any) -> str:
        if not self._is_allowed(event):
            return "ComfyUI 助手已关闭，或当前用户没有使用权限。"
        payload = await self._reference_context.image_spell_payload(event)
        return self._format_spell_payload(payload)

    async def reverse(self, event: Any) -> str:
        if not self._is_allowed(event):
            return "ComfyUI 助手已关闭，或当前用户没有使用权限。"
        image_input = await self._event_image_input(event)
        tags = await self._reference_context.reverse_image_tags(event, image_input)
        if not tags:
            return "图片反推失败：没有可用图片或视觉模型调用失败。"
        return "图片反推 tags：\n" + self._shorten(tags, 2200)

    async def upscale(self, event: Any) -> str:
        if not self._is_allowed(event):
            return "ComfyUI 助手已关闭，或当前用户没有使用权限。"
        ready = await self._ensure_ready(event)
        if not ready.get("ok"):
            return await self._send_payload(event, ready)
        image_input = await self._event_image_input(event)
        if not image_input:
            return "放大失败：请在本次消息中附图，或引用一条包含图片的消息。"
        payload = await self._run_tool(["upscale", "--input", image_input])
        return await self._send_payload(event, payload)

    async def remove_bg(self, event: Any) -> str:
        return "去背景功能暂未开放。当前先保留文生图、法术解析和图片反推主线。"

    async def handle_action(self, event: Any, action: str, prompt: str) -> str | None:
        """Handle one parsed command action.

        Args:
            event: AstrBot message event.
            action: Parsed action key from `command_router`.
            prompt: Prompt text after the action keyword.

        Returns:
            Optional message to send back. Generation returns None because it
            sends image results directly.
        """
        if not self._is_allowed(event):
            return "ComfyUI 助手已关闭，或当前用户没有使用权限。"
        if action == "help":
            return help_text(self._bool("img2img_enabled", False))
        if action == "status":
            return self.status_text(await self._run_tool(["status"]))
        if action == "diagnose":
            return self.diagnose_text(await self._run_tool(["status"]))
        if action == "debug_status":
            return self._task_recorder.debug_status_text(self.config)
        if action == "set_artist_tags":
            return self.set_artist_tags(prompt)
        if action == "create_artist_preset":
            return self.create_artist_preset(prompt)
        if action == "append_artist_tags":
            return self.append_artist_tags(prompt)
        if action == "use_artist_preset":
            return self.use_artist_preset(prompt)
        if action == "list_artist_presets":
            return self.list_artist_presets()
        if action == "delete_artist_preset":
            return self.delete_artist_preset(prompt)
        if action == "add_fixed_character":
            return self.add_fixed_character(prompt)
        if action == "generate":
            if not prompt:
                return "请在后面写完整 prompt 或 tags。"
            prompt, size, size_error = parse_generation_size(
                prompt,
                allowed_sizes(self.config, DEFAULT_GENERATION_SIZES),
            )
            if size_error:
                return size_error
            if not prompt:
                return "请在尺寸后面写完整 prompt 或 tags。"
            await self._generate(
                event,
                prompt,
                width=size[0] if size else None,
                height=size[1] if size else None,
            )
            return None
        if action == "multi_person":
            if not prompt:
                return (
                    "请描述至少两个人物。例："
                    "/anm 多人 左边若叶睦抱着吉他，右边千早爱音牵着她的手"
                )
            sizes = allowed_sizes(self.config, DEFAULT_GENERATION_SIZES)
            prompt, size, size_error = parse_generation_size(prompt, sizes)
            if size_error:
                return size_error
            if not prompt:
                return "请在尺寸后面描述至少两个人物。"
            if size is None and sizes:
                prompt_lower = prompt.lower()
                three_or_more = bool(
                    re.search(
                        r"(?:三|四|3|4)\s*(?:人|个|名|girls?|boys?|people)|"
                        r"\b(?:3|4)(?:girls?|boys?|people)\b",
                        prompt_lower,
                    )
                )
                vertically_stacked = any(
                    marker in prompt_lower
                    for marker in (
                        "骑在肩",
                        "骑肩",
                        "肩膀上",
                        "背着",
                        "抱起",
                        "扑倒",
                        "压在",
                        "上下叠",
                        "on the shoulders",
                        "piggyback",
                        "carrying",
                        "on top of",
                        "stacked",
                    )
                )
                physical_contact = any(
                    marker in prompt_lower
                    for marker in (
                        "牵手",
                        "拥抱",
                        "接吻",
                        "搂着",
                        "抱着",
                        "挽着",
                        "holding hands",
                        "hugging",
                        "embracing",
                        "kissing",
                        "arm around",
                    )
                )
                target = (
                    (1216, 832)
                    if three_or_more
                    else (1024, 1536)
                    if vertically_stacked
                    else (1024, 1024)
                    if physical_contact
                    else (1152, 896)
                )
                size = min(
                    sizes,
                    key=lambda candidate: (
                        abs((candidate[0] / candidate[1]) - (target[0] / target[1])),
                        abs(candidate[0] * candidate[1] - target[0] * target[1]),
                    ),
                )
            await self._generate(
                event,
                prompt,
                width=size[0] if size else None,
                height=size[1] if size else None,
                negative_prompt=join_prompt_parts(
                    [
                        str(
                            self.config.get("negative_prompt")
                            or DEFAULT_NEGATIVE_PROMPT
                        ),
                        ", ".join(MULTI_PERSON_NEGATIVE_TAGS),
                    ]
                ),
                multi_person=True,
            )
            return None
        if action == "edit":
            if not prompt:
                return "请在后面写改图 prompt。"
            return await self.edit(event, prompt)
        if action == "disabled_upscale":
            return "放大功能已关闭。"
        if action == "disabled_remove_bg":
            return await self.remove_bg(event)
        if action == "spell":
            return await self.spell(event)
        if action == "reverse":
            return await self.reverse(event)
        return "未知 Anima 指令。"
