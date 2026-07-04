from __future__ import annotations

import json
import os
from typing import Any, Callable

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent
from astrbot.core.utils.quoted_message.onebot_client import OneBotClient

try:
    from .image_storage import SUPPORTED_IMAGE_EXTS
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from image_storage import SUPPORTED_IMAGE_EXTS


class OneBotImageResolver:
    """Resolve current or quoted OneBot image segments without changing save behavior."""

    def __init__(
        self,
        *,
        logger: Any,
        shorten: Callable[[str, int], str],
        image_component_details: Callable[[Comp.Image], dict[str, str]],
        save_base64_image: Callable[..., str | None],
        save_media_ref_image: Callable[..., Any],
        save_image_component: Callable[..., Any],
    ):
        self._logger = logger
        self._shorten = shorten
        self._image_component_details = image_component_details
        self._save_base64_image = save_base64_image
        self._save_media_ref_image = save_media_ref_image
        self._save_image_component = save_image_component

    def reply_ids_from_raw_event(self, event: AstrMessageEvent) -> list[str]:
        """Extract OneBot reply ids from the raw current event."""
        raw = getattr(event.message_obj, "raw_message", None)
        segments = raw.get("message") if hasattr(raw, "get") else None
        if not isinstance(segments, list):
            return []
        reply_ids = []
        for segment in segments:
            if not isinstance(segment, dict) or segment.get("type") != "reply":
                continue
            data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
            reply_id = data.get("id")
            if reply_id is not None:
                reply_ids.append(str(reply_id))
        return reply_ids

    def _client(self, event: AstrMessageEvent) -> OneBotClient | None:
        client = OneBotClient(event)
        bot = getattr(event, "bot", None)
        direct_call_action = getattr(bot, "call_action", None)
        if getattr(client, "_call_action", None) is None and callable(direct_call_action):
            client._call_action = direct_call_action
        if getattr(client, "_call_action", None) is None:
            return None
        return client

    def _image_from_segment(self, data: dict[str, Any]) -> Comp.Image:
        return Comp.Image(
            file=str(data.get("file") or data.get("url") or data.get("path") or data.get("file_id") or data.get("id") or ""),
            url=str(data.get("url") or ""),
            path=str(data.get("path") or ""),
            _type=str(data.get("sub_type") or data.get("type") or ""),
        )

    def _candidate_values(self, data: dict[str, Any]) -> list[str]:
        values = [
            str(data.get("path") or "").strip(),
            str(data.get("file") or "").strip(),
            str(data.get("file_id") or "").strip(),
            str(data.get("id") or "").strip(),
            str(data.get("url") or "").strip(),
        ]
        seen: set[str] = set()
        candidates: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            candidates.append(value)
        return candidates

    def _image_ids(self, candidate: str) -> list[str]:
        ids = [candidate]
        base_name, ext = os.path.splitext(candidate)
        if ext.lower() in SUPPORTED_IMAGE_EXTS and base_name:
            ids.append(base_name)
        return ids

    def _group_id_value(self, event: AstrMessageEvent) -> str | int | None:
        try:
            group_id = event.get_group_id()
        except Exception:
            group_id = None
        if isinstance(group_id, str) and group_id.isdigit():
            return int(group_id)
        return group_id

    def _actions_for(self, event: AstrMessageEvent, image_ids: list[str]) -> list[tuple[str, dict[str, Any]]]:
        actions: list[tuple[str, dict[str, Any]]] = []
        for image_id in image_ids:
            actions.extend(
                [
                    ("get_image", {"file": image_id}),
                    ("get_image", {"file_id": image_id}),
                    ("get_image", {"id": image_id}),
                    ("get_image", {"image": image_id}),
                    ("get_file", {"file_id": image_id}),
                    ("get_file", {"file": image_id}),
                ]
            )
        group_id_value = self._group_id_value(event)
        if group_id_value:
            for image_id in image_ids:
                actions.append(("get_group_file_url", {"group_id": group_id_value, "file_id": image_id}))
        for image_id in image_ids:
            actions.append(("get_private_file_url", {"file_id": image_id}))
        return actions

    def _media_refs(self, resolved_data: dict[str, Any]) -> list[str]:
        refs = [
            str(resolved_data.get("file") or "").strip(),
            str(resolved_data.get("path") or "").strip(),
            str(resolved_data.get("file_path") or "").strip(),
            str(resolved_data.get("url") or "").strip(),
        ]
        seen: set[str] = set()
        media_refs: list[str] = []
        for ref in refs:
            if not ref or ref in seen:
                continue
            seen.add(ref)
            media_refs.append(ref)
        return media_refs

    def _original_name(self, data: dict[str, Any], resolved_data: dict[str, Any] | None = None) -> str:
        resolved_data = resolved_data or {}
        return str(
            resolved_data.get("file_name")
            or data.get("file")
            or data.get("url")
            or "image.png"
        )

    async def _save_segment_image(
        self,
        event: AstrMessageEvent,
        *,
        client: OneBotClient,
        data: dict[str, Any],
        label: str,
        index: int,
        source: str,
        log_prefix: str,
        extra_details: dict[str, Any] | None = None,
        fallback_component: bool = False,
    ) -> str | None:
        image = self._image_from_segment(data)
        self._logger.info(
            "[comfyui_agent] %s image segment index=%s data=%s",
            log_prefix,
            index,
            self._shorten(json.dumps(data, ensure_ascii=False), 1000),
        )
        details = self._image_component_details(image)
        details["source"] = source
        details["label"] = label
        details["raw_segment"] = self._shorten(json.dumps(data, ensure_ascii=False), 1000)
        if extra_details:
            details.update(extra_details)

        for candidate in self._candidate_values(data):
            for action, params in self._actions_for(event, self._image_ids(candidate)):
                resolved_data = await client.call(
                    action,
                    params,
                    warn_on_all_failed=False,
                    unwrap_data=True,
                )
                if not isinstance(resolved_data, dict):
                    continue
                self._logger.info(
                    "[comfyui_agent] %s media resolved action=%s params=%s keys=%s file=%s url=%s base64=%s",
                    log_prefix,
                    action,
                    params,
                    sorted(resolved_data.keys()),
                    self._shorten(str(resolved_data.get("file") or resolved_data.get("path") or resolved_data.get("file_path") or ""), 260),
                    self._shorten(str(resolved_data.get("url") or ""), 260),
                    "yes" if resolved_data.get("base64") else "no",
                )
                saved = self._save_base64_image(
                    event,
                    str(resolved_data.get("base64") or ""),
                    label,
                    index,
                    original=self._original_name(data, resolved_data),
                    details={**details, "resolve_action": action, "resolve_params": params},
                )
                if saved:
                    return saved
                for media_ref in self._media_refs(resolved_data):
                    saved = await self._save_media_ref_image(
                        event,
                        media_ref,
                        label,
                        index,
                        original=self._original_name(data),
                        details={**details, "resolve_action": action},
                    )
                    if saved:
                        return saved
        if fallback_component:
            return await self._save_image_component(event, image, label, index)
        return None

    async def save_raw_message_image(
        self,
        event: AstrMessageEvent,
        data: dict[str, Any],
        label: str,
        index: int,
    ) -> str | None:
        """Save the first resolvable image from a raw OneBot image segment."""
        client = self._client(event)
        if client is None:
            return None
        return await self._save_segment_image(
            event,
            client=client,
            data=data,
            label=label,
            index=index,
            source="raw_message",
            log_prefix="raw",
        )

    async def save_reply_image(self, event: AstrMessageEvent) -> str | None:
        """Save the first resolvable image from a quoted OneBot message."""
        client = self._client(event)
        if client is None:
            return None
        for reply_id in self.reply_ids_from_raw_event(event):
            try:
                reply_data = await client.get_msg(reply_id)
            except Exception as exc:
                self._logger.warning("[comfyui_agent] failed to fetch raw reply message %s: %s", reply_id, exc)
                continue
            segments = reply_data.get("message") if isinstance(reply_data, dict) else None
            if not isinstance(segments, list):
                continue
            image_index = 0
            for segment in segments:
                if not isinstance(segment, dict) or segment.get("type") != "image":
                    continue
                data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
                image_index += 1
                saved = await self._save_segment_image(
                    event,
                    client=client,
                    data=data,
                    label="reply",
                    index=image_index,
                    source="onebot_reply",
                    log_prefix="reply",
                    extra_details={"reply_id": str(reply_id)},
                    fallback_component=True,
                )
                if saved:
                    return saved
        return None


# Backward-compatible alias for code that still imports the old name.
OneBotReplyImageResolver = OneBotImageResolver
