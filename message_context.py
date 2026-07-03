from __future__ import annotations

import re
from typing import Any, Callable

import astrbot.api.message_components as Comp


REFERENCE_PROMPT_MARKERS = (
    "参考引用图",
    "引用图",
    "参考这张图",
    "参考这图",
    "按这张图",
    "照这张图",
    "照着这张图",
    "根据这张图",
    "用这张图",
    "以这张图",
    "图中角色",
    "图里的角色",
    "图中衣服",
    "图里的衣服",
    "同款衣服",
    "参考图片",
    "参考图",
)


class MessageContextBuilder:
    """Build prompt context from chat messages and quoted content."""

    def __init__(
        self,
        *,
        reference_context: Any,
        event_image_input: Callable[[Any], Any],
        logger: Any,
        get_bool: Callable[[str, bool], bool],
        shorten: Callable[[str, int], str],
    ):
        """Store dependencies for message-context enrichment.

        Args:
            reference_context: Image reference-context builder.
            event_image_input: Image input resolver callback.
            logger: Logger compatible with AstrBot logger methods.
            get_bool: Config boolean accessor.
            shorten: Text-shortening helper.
        """
        self._reference_context = reference_context
        self._event_image_input = event_image_input
        self._logger = logger
        self._bool = get_bool
        self._shorten = shorten

    def reply_texts(self, event: Any) -> list[str]:
        """Collect text from quoted reply components.

        Args:
            event: AstrBot message event.

        Returns:
            Non-empty reply text snippets.
        """
        texts = []
        for component in event.get_messages():
            if not isinstance(component, Comp.Reply):
                continue
            message = str(component.message_str or component.text or "").strip()
            if message:
                texts.append(message)
        return texts

    def extract_spell_prompts(self, text: str) -> tuple[str, str] | None:
        """Extract positive and negative prompts from a spell result text.

        Args:
            text: Quoted message text.

        Returns:
            Positive and negative prompt pair, or None when not found.
        """
        if "法术解析结果" not in text or "正面提示词" not in text:
            return None
        positive_match = re.search(
            r"正面提示词[：:]\s*(.*?)(?:\n\s*负面提示词[：:]|\Z)",
            text,
            flags=re.S,
        )
        if not positive_match:
            return None
        positive = positive_match.group(1).strip()
        negative = ""
        negative_match = re.search(r"负面提示词[：:]\s*(.*)\Z", text, flags=re.S)
        if negative_match:
            negative = negative_match.group(1).strip()
        if not positive:
            return None
        return self._shorten(positive, 3500), self._shorten(negative, 1600)

    def wants_quoted_prompt(self, prompt: str) -> bool:
        """Check whether the prompt asks to reuse quoted prompt text.

        Args:
            prompt: User prompt.

        Returns:
            True when quoted prompt/spell text should be inspected.
        """
        text = str(prompt or "")
        if "引用" not in text:
            return False
        return any(marker in text for marker in ("提示词", "法术", "tags", "tag", "咒语"))

    def wants_reference_image(self, prompt: str) -> bool:
        """Check whether the prompt asks to use an attached or quoted image.

        Args:
            prompt: User prompt.

        Returns:
            True when image reference context should be attempted.
        """
        text = str(prompt or "")
        return any(marker in text for marker in REFERENCE_PROMPT_MARKERS)

    def augment_prompt_with_quoted_spell(self, event: Any, prompt: str) -> str:
        """Augment a prompt with quoted spell metadata when available.

        Args:
            event: AstrBot message event.
            prompt: Current prompt text.

        Returns:
            Original or augmented prompt.
        """
        if not self.wants_quoted_prompt(prompt):
            return prompt
        for text in self.reply_texts(event):
            extracted = self.extract_spell_prompts(text)
            if not extracted:
                continue
            positive, negative = extracted
            lines = [
                f"用户要求：{prompt}",
                "引用法术正面提示词：",
                positive,
            ]
            if negative:
                lines.extend(["引用法术负面提示词：", negative])
            lines.append(
                "处理要求：借鉴引用法术中的服饰、动作、构图、氛围和风格；"
                "如果用户指定了固定角色，只保留固定角色自身设定，不要复制引用法术里的角色身份、发色、眼色、年龄、种族等固有设定。"
            )
            augmented = "\n".join(lines)
            self._logger.info("[comfyui_agent] prompt augmented with quoted spell chars=%s", len(augmented))
            return augmented
        self._logger.info("[comfyui_agent] quoted prompt requested but no spell result found in reply")
        return prompt

    async def augment_prompt_with_reference_image(self, event: Any, prompt: str) -> str | None:
        """Augment a prompt with reference image context when requested.

        Args:
            event: AstrBot message event.
            prompt: Current prompt text.

        Returns:
            Original prompt, augmented prompt, or None when a requested image is missing.
        """
        if not self.wants_reference_image(prompt):
            return prompt
        image_input = await self._event_image_input(event)
        if self._bool("debug_image_reference_enabled", False):
            self._logger.info("[comfyui_agent] reference image requested input=%s", image_input or "none")
        if not image_input:
            self._logger.info("[comfyui_agent] reference image requested but no image component found")
            return None
        reference = await self._reference_context.reference_prompt_context(event, image_input)
        if self._bool("debug_image_reference_enabled", False):
            self._logger.info(
                "[comfyui_agent] reference image context chars=%s content=%s",
                len(reference),
                self._shorten(reference, 3000),
            )
        if not reference:
            return prompt
        self._logger.info("[comfyui_agent] prompt augmented with image reference chars=%s", len(reference))
        return f"用户要求：{prompt}\n{reference}"

    def format_spell_payload(self, payload: dict[str, Any]) -> str:
        """Render a chat-visible spell extraction result.

        Args:
            payload: Spell payload returned by the image prompt helper.

        Returns:
            Human-readable spell extraction text.
        """
        if not payload.get("ok"):
            return f"法术解析失败：{payload.get('error') or 'unknown_error'}"
        positive = str(payload.get("positive_prompt") or "").strip()
        negative = str(payload.get("negative_prompt") or "").strip()
        params = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
        lines = [
            "法术解析结果：",
            f"- 格式：{payload.get('metadata_format') or '未识别到生成信息'}",
            f"- 尺寸：{payload.get('width')}x{payload.get('height')}",
        ]
        if params:
            compact_params = []
            for key in ("steps", "Steps", "cfg", "CFG scale", "sampler_name", "Sampler", "scheduler", "seed", "Seed", "size", "Size"):
                if key in params:
                    compact_params.append(f"{key}={params[key]}")
            if compact_params:
                lines.append(f"- 参数：{', '.join(compact_params)}")
        lines.append("")
        lines.append("正面提示词：")
        if positive:
            lines.append(self._shorten(positive, 2200))
        elif str(payload.get("format") or "").upper() == "JPEG" and payload.get("metadata_keys") == ["jfif", "jfif_density", "jfif_unit", "jfif_version"]:
            lines.append("未读取到正面提示词。这张图是 QQ/NapCat 取回的 JPEG 副本，生成信息大概率已经被平台转码时去掉。")
        else:
            lines.append("未读取到正面提示词")
        if negative:
            lines.append("")
            lines.append("负面提示词：")
            lines.append(self._shorten(negative, 1000))
        return "\n".join(lines)
