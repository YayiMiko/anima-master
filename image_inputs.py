import base64
from pathlib import Path
from typing import Any, Callable

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent
from astrbot.core.utils.media_utils import MediaResolver

try:
    from .image_manifest import ImageInputManifest
    from .image_storage import ImageInputStorage
    from .onebot_image_resolver import OneBotReplyImageResolver
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from image_manifest import ImageInputManifest
    from image_storage import ImageInputStorage
    from onebot_image_resolver import OneBotReplyImageResolver


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
        self._manifest = ImageInputManifest(
            workspace=self.workspace,
            inputs_dir=self.inputs_dir,
        )
        self._storage = ImageInputStorage(self._manifest)
        self._onebot_reply_images = OneBotReplyImageResolver(
            logger=self._logger,
            shorten=self._shorten,
            image_component_details=self._image_component_details,
            save_base64_image=self._save_base64_image,
            save_media_ref_image=self._save_media_ref_image,
            save_image_component=self._save_image_component,
        )
        self.last_summary: dict[str, Any] = {}

    def _safe_name(self, value: str, fallback: str = "image") -> str:
        return self._manifest.safe_name(value, fallback)

    def _input_target_dir(self, event: AstrMessageEvent) -> Path:
        return self._manifest.input_target_dir(event)

    def _write_input_record(
        self,
        event: AstrMessageEvent,
        target: Path,
        original: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._manifest.write_input_record(event, target, original, details=details)
        self.last_summary = dict(self._manifest.last_summary)

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
        target = self._storage.copy_file(
            event,
            source,
            label=label,
            index=index,
            original=str(original),
        )
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
                target = self._storage.copy_file(
                    event,
                    source,
                    label=label,
                    index=index,
                    original=str(original_name),
                    mime_type=str(resolved.mime_type or ""),
                )

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
        target = self._storage.write_bytes(
            event,
            image_bytes,
            label=label,
            index=index,
            original=str(original_name),
        )

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

    async def _save_onebot_reply_image(self, event: AstrMessageEvent) -> str | None:
        return await self._onebot_reply_images.save_reply_image(event)

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
