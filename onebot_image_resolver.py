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


class OneBotReplyImageResolver:
    """Resolve images from quoted OneBot messages without changing save behavior."""

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

    async def save_reply_image(self, event: AstrMessageEvent) -> str | None:
        """Save the first resolvable image from a quoted OneBot message."""
        client = OneBotClient(event)
        bot = getattr(event, "bot", None)
        direct_call_action = getattr(bot, "call_action", None)
        if getattr(client, "_call_action", None) is None and callable(direct_call_action):
            client._call_action = direct_call_action
        if getattr(client, "_call_action", None) is None:
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
                image = Comp.Image(
                    file=str(data.get("file") or data.get("url") or ""),
                    url=str(data.get("url") or ""),
                    path=str(data.get("path") or ""),
                    _type=str(data.get("sub_type") or data.get("type") or ""),
                )
                self._logger.info(
                    "[comfyui_agent] raw reply image segment reply_id=%s index=%s data=%s",
                    reply_id,
                    image_index,
                    self._shorten(json.dumps(data, ensure_ascii=False), 1000),
                )
                details = self._image_component_details(image)
                details["source"] = "onebot_reply"
                details["reply_id"] = str(reply_id)
                details["raw_segment"] = self._shorten(json.dumps(data, ensure_ascii=False), 1000)
                candidates = [
                    str(data.get("path") or "").strip(),
                    str(data.get("file") or "").strip(),
                    str(data.get("file_id") or "").strip(),
                    str(data.get("url") or "").strip(),
                ]
                seen_candidates: set[str] = set()
                for candidate in [item for item in candidates if item]:
                    if candidate in seen_candidates:
                        continue
                    seen_candidates.add(candidate)
                    image_ids = [candidate]
                    base_name, ext = os.path.splitext(candidate)
                    if ext.lower() in SUPPORTED_IMAGE_EXTS and base_name:
                        image_ids.append(base_name)

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
                    try:
                        group_id = event.get_group_id()
                    except Exception:
                        group_id = None
                    group_id_value: str | int | None = group_id
                    if isinstance(group_id, str) and group_id.isdigit():
                        group_id_value = int(group_id)
                    if group_id_value:
                        for image_id in image_ids:
                            actions.append(
                                (
                                    "get_group_file_url",
                                    {"group_id": group_id_value, "file_id": image_id},
                                )
                            )
                    for image_id in image_ids:
                        actions.append(("get_private_file_url", {"file_id": image_id}))

                    for action, params in actions:
                        resolved_data = await client.call(
                            action,
                            params,
                            warn_on_all_failed=False,
                            unwrap_data=True,
                        )
                        if not isinstance(resolved_data, dict):
                            continue
                        self._logger.info(
                            "[comfyui_agent] reply media resolved action=%s params=%s keys=%s file=%s url=%s base64=%s",
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
                            "reply",
                            image_index,
                            original=str(
                                resolved_data.get("file_name")
                                or data.get("file")
                                or data.get("url")
                                or "image.png"
                            ),
                            details={**details, "resolve_action": action, "resolve_params": params},
                        )
                        if saved:
                            return saved
                        media_refs = [
                            str(resolved_data.get("file") or "").strip(),
                            str(resolved_data.get("path") or "").strip(),
                            str(resolved_data.get("file_path") or "").strip(),
                            str(resolved_data.get("url") or "").strip(),
                        ]
                        seen_refs: set[str] = set()
                        for media_ref in [item for item in media_refs if item]:
                            if media_ref in seen_refs:
                                continue
                            seen_refs.add(media_ref)
                            saved = await self._save_media_ref_image(
                                event,
                                media_ref,
                                "reply",
                                image_index,
                                original=str(data.get("file") or data.get("url") or "image.png"),
                                details={**details, "resolve_action": action},
                            )
                            if saved:
                                return saved
                saved = await self._save_image_component(event, image, "reply", image_index)
                if saved:
                    return saved
        return None
