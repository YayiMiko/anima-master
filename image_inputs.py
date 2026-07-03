import base64
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Callable

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent
from astrbot.core.utils.media_utils import MediaResolver
from astrbot.core.utils.quoted_message.onebot_client import OneBotClient

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class ImageInputResolver:
    """Resolve chat images into local workspace files for Anima tasks."""

    def __init__(
        self,
        *,
        workspace: Path,
        inputs_dir: Path,
        logger: Any,
        shorten: Callable[[str, int], str],
    ):
        """Create an image resolver.

        Args:
            workspace: AstrBot workspace path.
            inputs_dir: Directory where input images and manifests are stored.
            logger: Logger-like object used for diagnostics.
            shorten: Function used to shorten long debug strings.
        """
        self.workspace = Path(workspace)
        self.inputs_dir = Path(inputs_dir)
        self._logger = logger
        self._shorten = shorten
        self.last_summary: dict[str, Any] = {}

    def _safe_name(self, value: str, fallback: str = "image") -> str:
        name = Path(str(value).replace("\\", "/")).name.strip()
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = name.strip(" .")
        return name or fallback

    def _input_target_dir(self, event: AstrMessageEvent) -> Path:
        date_dir = datetime.now().strftime("%Y%m%d")
        session = self._safe_name(event.get_session_id() or "session", "session")
        target_dir = self.inputs_dir / date_dir / session
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def _write_input_record(
        self,
        event: AstrMessageEvent,
        target: Path,
        original: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.inputs_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "platform_id": event.get_platform_id(),
            "session_id": event.get_session_id(),
            "sender_id": event.get_sender_id(),
            "kind": "image",
            "original_name": self._safe_name(original, "image"),
            "path": str(target),
            "relative_path": str(target.relative_to(self.workspace)),
            "size": target.stat().st_size,
            "source": "comfyui_hard_route",
        }
        if details:
            record["details"] = details
        manifest = self.inputs_dir / "manifest.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        (self.inputs_dir / "latest.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.last_summary = {
            "path": str(target),
            "source": str(details.get("source") if details else record["source"]),
            "label": str(details.get("label") if details else ""),
            "size": record["size"],
            "original_name": record["original_name"],
        }

    def _image_component_details(self, component: Comp.Image) -> dict[str, str]:
        return {
            "file": self._shorten(str(component.file or ""), 500),
            "url": self._shorten(str(component.url or ""), 500),
            "path": self._shorten(str(component.path or ""), 500),
            "type": self._shorten(str(getattr(component, "_type", "") or ""), 120),
        }

    async def _save_image_component(
        self,
        event: AstrMessageEvent,
        component: Comp.Image,
        label: str,
        index: int,
    ) -> str | None:
        try:
            source = Path(await component.convert_to_file_path())
        except Exception as exc:
            self._logger.warning("[comfyui_agent] failed to resolve %s image: %s", label, exc)
            return None
        if not source.exists() or not source.is_file():
            self._logger.warning("[comfyui_agent] resolved %s image does not exist: %s", label, source)
            return None
        original = component.file or component.url or source.name or "image.png"
        ext = Path(str(original)).suffix.lower() or source.suffix.lower()
        if ext not in SUPPORTED_IMAGE_EXTS:
            ext = ".png"
        timestamp = datetime.now().strftime("%H%M%S%f")
        sender = self._safe_name(event.get_sender_id() or "unknown", "unknown")
        filename = f"{timestamp}_{sender}_{label}_image_{index}{ext}"
        target = self._input_target_dir(event) / filename
        shutil.copy2(source, target)
        details = self._image_component_details(component)
        details["source"] = "component"
        details["label"] = label
        details["resolved_source"] = self._shorten(str(source), 500)
        self._write_input_record(event, target, original, details=details)
        self._logger.info(
            "[comfyui_agent] saved %s image input: %s file=%s url=%s path=%s source=%s",
            label,
            target,
            details.get("file"),
            details.get("url"),
            details.get("path"),
            details.get("resolved_source"),
        )
        return str(target)

    async def _save_media_ref_image(
        self,
        event: AstrMessageEvent,
        image_ref: str,
        label: str,
        index: int,
        *,
        original: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str | None:
        try:
            async with MediaResolver(
                image_ref,
                media_type="image",
                default_suffix=".bin",
            ).as_path() as resolved:
                source = resolved.path
                if not source.exists() or not source.is_file():
                    self._logger.warning("[comfyui_agent] resolved %s media ref does not exist: %s", label, source)
                    return None

                original_name = original or image_ref or source.name or "image.png"
                ext = Path(str(original_name)).suffix.lower() or source.suffix.lower()
                if ext not in SUPPORTED_IMAGE_EXTS:
                    mime_exts = {
                        "image/jpeg": ".jpg",
                        "image/png": ".png",
                        "image/webp": ".webp",
                        "image/bmp": ".bmp",
                    }
                    ext = mime_exts.get(str(resolved.mime_type or "").lower(), ".png")

                timestamp = datetime.now().strftime("%H%M%S%f")
                sender = self._safe_name(event.get_sender_id() or "unknown", "unknown")
                filename = f"{timestamp}_{sender}_{label}_image_{index}{ext}"
                target = self._input_target_dir(event) / filename
                shutil.copy2(source, target)

                record_details = dict(details or {})
                record_details["source"] = str(record_details.get("source") or "media_ref")
                record_details["label"] = label
                record_details["resolved_ref"] = self._shorten(image_ref, 500)
                record_details["resolved_source"] = self._shorten(str(source), 500)
                record_details["resolved_mime_type"] = str(resolved.mime_type or "")
                self._write_input_record(event, target, original_name, details=record_details)
                self._logger.info(
                    "[comfyui_agent] saved %s image input from media ref: %s ref=%s source=%s",
                    label,
                    target,
                    self._shorten(image_ref, 500),
                    source,
                )
                return str(target)
        except Exception as exc:
            self._logger.warning("[comfyui_agent] failed to resolve %s media ref %s: %s", label, self._shorten(image_ref, 160), exc)
            return None

    def _save_base64_image(
        self,
        event: AstrMessageEvent,
        payload: str,
        label: str,
        index: int,
        *,
        original: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str | None:
        data = str(payload or "").strip()
        if not data:
            return None
        if data.startswith("base64://"):
            data = data.removeprefix("base64://")
        if data.startswith("data:"):
            header, separator, body = data.partition(",")
            if not separator or "base64" not in header.lower():
                return None
            data = body
        try:
            image_bytes = base64.b64decode("".join(data.split()), validate=False)
        except Exception as exc:
            self._logger.warning("[comfyui_agent] failed to decode %s base64 image: %s", label, exc)
            return None
        if not image_bytes:
            return None

        original_name = original or "image.png"
        ext = Path(str(original_name)).suffix.lower()
        if ext not in SUPPORTED_IMAGE_EXTS:
            ext = ".png"
        timestamp = datetime.now().strftime("%H%M%S%f")
        sender = self._safe_name(event.get_sender_id() or "unknown", "unknown")
        filename = f"{timestamp}_{sender}_{label}_image_{index}{ext}"
        target = self._input_target_dir(event) / filename
        target.write_bytes(image_bytes)

        record_details = dict(details or {})
        record_details["source"] = str(record_details.get("source") or "base64")
        record_details["label"] = label
        record_details["resolved_base64_bytes"] = str(len(image_bytes))
        self._write_input_record(event, target, original_name, details=record_details)
        self._logger.info(
            "[comfyui_agent] saved %s image input from base64: %s bytes=%s",
            label,
            target,
            len(image_bytes),
        )
        return str(target)

    def _reply_ids_from_raw_event(self, event: AstrMessageEvent) -> list[str]:
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

    async def _save_onebot_reply_image(self, event: AstrMessageEvent) -> str | None:
        client = OneBotClient(event)
        bot = getattr(event, "bot", None)
        direct_call_action = getattr(bot, "call_action", None)
        if getattr(client, "_call_action", None) is None and callable(direct_call_action):
            client._call_action = direct_call_action
        if getattr(client, "_call_action", None) is None:
            return None
        for reply_id in self._reply_ids_from_raw_event(event):
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

    async def event_image_input(self, event: AstrMessageEvent) -> str | None:
        """Resolve the intended image from direct or quoted chat content.

        Args:
            event: Current AstrBot message event.

        Returns:
            The saved local image path, or None when no usable image is found.
        """
        self.last_summary = {}
        direct_images: list[Comp.Image] = []
        reply_images: list[Comp.Image] = []
        for component in event.get_messages():
            if isinstance(component, Comp.Image):
                direct_images.append(component)
            elif isinstance(component, Comp.Reply):
                for inner in component.chain or []:
                    if isinstance(inner, Comp.Image):
                        reply_images.append(inner)

        if reply_images:
            saved = await self._save_onebot_reply_image(event)
            if saved:
                return saved
        for index, image in enumerate(reply_images or direct_images, start=1):
            saved = await self._save_image_component(
                event,
                image,
                "reply" if reply_images else "message",
                index,
            )
            if saved:
                return saved
        self.last_summary = {
            "path": "",
            "source": "not_found",
            "reply_images": len(reply_images),
            "direct_images": len(direct_images),
        }
        return None
