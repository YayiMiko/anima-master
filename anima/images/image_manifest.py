from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent


class ImageInputManifest:
    """Persist input image manifest records and latest-image pointers."""

    def __init__(self, *, workspace: Path, inputs_dir: Path):
        """Create a manifest writer.

        Args:
            workspace: AstrBot workspace path.
            inputs_dir: Directory where image inputs and manifest files live.
        """
        self.workspace = Path(workspace)
        self.inputs_dir = Path(inputs_dir)
        self._lock = threading.RLock()

    def safe_name(self, value: str, fallback: str = "image") -> str:
        """Return a filesystem-safe leaf name."""
        name = Path(str(value).replace("\\", "/")).name.strip()
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = name.strip(" .")
        return name or fallback

    def input_target_dir(self, event: AstrMessageEvent) -> Path:
        """Return the dated per-session and per-sender input directory."""
        date_dir = datetime.now().strftime("%Y%m%d")
        session = self.safe_name(event.get_session_id() or "session", "session")
        sender = self.safe_name(event.get_sender_id() or "unknown", "unknown")
        target_dir = self.inputs_dir / date_dir / session / sender
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def write_input_record(
        self,
        event: AstrMessageEvent,
        target: Path,
        original: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append an image record and update latest.json."""
        self.inputs_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "platform_id": event.get_platform_id(),
            "session_id": event.get_session_id(),
            "sender_id": event.get_sender_id(),
            "kind": "image",
            "original_name": self.safe_name(original, "image"),
            "path": str(target),
            "relative_path": str(target.relative_to(self.workspace)),
            "size": target.stat().st_size,
            "source": "comfyui_hard_route",
        }
        if details:
            record["details"] = details
        manifest = self.inputs_dir / "manifest.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        session_latest = target.parent / "latest.json"
        with self._lock:
            with manifest.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            temporary = session_latest.with_name(
                f".{session_latest.name}.{uuid.uuid4().hex}.tmp"
            )
            temporary.write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, session_latest)
        return record
