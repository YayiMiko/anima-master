from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image


def coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    return str(value)


def image_metadata(path: Path) -> dict[str, str]:
    with Image.open(path) as image:
        return {str(key): coerce_text(value) for key, value in image.info.items()}


def image_summary(path: Path, workspace: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input": str(path),
        "relative_path": str(path.relative_to(workspace)) if path.is_relative_to(workspace) else None,
        "size": path.stat().st_size,
        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }
    with Image.open(path) as image:
        payload.update({"width": image.width, "height": image.height, "format": image.format, "mode": image.mode})
    return payload
