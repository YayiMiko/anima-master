from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

try:
    from .image_manifest import ImageInputManifest
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from image_manifest import ImageInputManifest

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent


SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MIME_IMAGE_EXTS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


class ImageInputStorage:
    """Save resolved image data into the workspace inputs directory."""

    def __init__(self, manifest: ImageInputManifest):
        self._manifest = manifest

    def extension_for(
        self,
        original: str,
        *,
        source_suffix: str = "",
        mime_type: str = "",
    ) -> str:
        """Choose a supported image extension for a saved input."""
        ext = Path(str(original or "")).suffix.lower() or str(source_suffix or "").lower()
        if ext in SUPPORTED_IMAGE_EXTS:
            return ext
        return MIME_IMAGE_EXTS.get(str(mime_type or "").lower(), ".png")

    def target_path(
        self,
        event: "AstrMessageEvent",
        *,
        label: str,
        index: int,
        extension: str,
    ) -> Path:
        """Return the destination path for one saved image."""
        ext = extension if extension in SUPPORTED_IMAGE_EXTS else ".png"
        timestamp = datetime.now().strftime("%H%M%S%f")
        sender = self._manifest.safe_name(event.get_sender_id() or "unknown", "unknown")
        filename = f"{timestamp}_{sender}_{label}_image_{index}{ext}"
        return self._manifest.input_target_dir(event) / filename

    def copy_file(
        self,
        event: "AstrMessageEvent",
        source: Path,
        *,
        label: str,
        index: int,
        original: str,
        mime_type: str = "",
    ) -> Path:
        """Copy a resolved image file into workspace inputs."""
        ext = self.extension_for(original, source_suffix=source.suffix, mime_type=mime_type)
        target = self.target_path(event, label=label, index=index, extension=ext)
        shutil.copy2(source, target)
        return target

    def write_bytes(
        self,
        event: "AstrMessageEvent",
        image_bytes: bytes,
        *,
        label: str,
        index: int,
        original: str,
    ) -> Path:
        """Write decoded image bytes into workspace inputs."""
        ext = self.extension_for(original)
        target = self.target_path(event, label=label, index=index, extension=ext)
        target.write_bytes(image_bytes)
        return target
