from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class ComfyUIImageResolver:
    """Resolve workspace input images for ComfyUI helper commands."""

    def __init__(self, workspace: Path, supported_exts: set[str] | None = None):
        self.workspace = Path(workspace)
        self.inputs = self.workspace / "inputs"
        self.manifest = self.inputs / "manifest.jsonl"
        self.latest_input = self.inputs / "latest.json"
        self.supported_exts = {
            item.lower() for item in (supported_exts or SUPPORTED_EXTS)
        }

    def inside_workspace(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.workspace.resolve())
        except ValueError:
            raise SystemExit(f"path is outside workspace: {path}")
        return resolved

    def manifest_records(self) -> list[dict[str, Any]]:
        if not self.manifest.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("kind") == "image":
                records.append(item)
        return records

    def path_from_record(self, record: dict[str, Any]) -> Path | None:
        value = record.get("path") or record.get("relative_path")
        if not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            path = self.workspace / path
        try:
            path = self.inside_workspace(path)
        except SystemExit:
            return None
        if (
            path.exists()
            and path.is_file()
            and path.suffix.lower() in self.supported_exts
        ):
            return path
        return None

    def recent_images(self, limit: int) -> list[Path]:
        records = list(reversed(self.manifest_records()))
        images: list[Path] = []
        seen: set[Path] = set()
        for record in records:
            path = self.path_from_record(record)
            if not path or path in seen:
                continue
            images.append(path)
            seen.add(path)
            if len(images) >= limit:
                break
        if images:
            return images
        candidates = [
            p
            for p in self.inputs.rglob("*")
            if p.is_file() and p.suffix.lower() in self.supported_exts
        ]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[:limit]

    def latest_image(self) -> Path:
        latest = _json_file(self.latest_input)
        path = self.path_from_record(latest)
        if path:
            return path
        recent = self.recent_images(1)
        if recent:
            return recent[0]
        raise SystemExit("no recent image found in workspace inputs")

    def resolve_image(self, value: str | None) -> Path:
        value = str(value or "latest").strip()
        if not value or value.lower() == "latest":
            return self.latest_image()
        if value.lower().startswith("recent:"):
            try:
                index = max(1, int(value.split(":", 1)[1]))
            except ValueError:
                index = 1
            recent = self.recent_images(index)
            if len(recent) >= index:
                return recent[index - 1]
            raise SystemExit("recent image not found")
        path = Path(value)
        if not path.is_absolute():
            path = self.workspace / path
        path = self.inside_workspace(path)
        if not path.exists() or not path.is_file():
            raise SystemExit(f"input image not found: {path}")
        if path.suffix.lower() not in self.supported_exts:
            raise SystemExit(f"unsupported input image type: {path.suffix}")
        return path


def _json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
