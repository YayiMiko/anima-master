from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class StorageRetentionManager:
    """Run bounded storage cleanup periodically for a long-lived plugin."""

    def __init__(
        self,
        *,
        inputs_dir: Path,
        outputs_dir: Path,
        tasks_dir: Path,
        retention_days: int,
        manifest_max_records: int,
        logger: Any,
        interval: int = 100,
    ):
        """Create a periodic retention manager.

        Args:
            inputs_dir: Plugin-owned workspace input directory.
            outputs_dir: Plugin-owned workspace output directory.
            tasks_dir: Per-request task record directory.
            retention_days: File age limit in days.
            manifest_max_records: Maximum manifest record count.
            logger: Logger-like object used for cleanup warnings.
            interval: Number of task writes between cleanup runs.
        """
        self._kwargs = {
            "inputs_dir": inputs_dir,
            "outputs_dir": outputs_dir,
            "tasks_dir": tasks_dir,
            "retention_days": retention_days,
            "manifest_max_records": manifest_max_records,
            "logger": logger,
        }
        self._interval = max(1, interval)
        self._writes = 0

    def run(self, *, force: bool = False) -> dict[str, int] | None:
        """Run cleanup now or after the configured write interval.

        Args:
            force: Whether to ignore the write interval.

        Returns:
            Cleanup counts when a run occurs, otherwise None.
        """
        self._writes += 1
        if not force and self._writes % self._interval:
            return None
        return prune_storage(**self._kwargs)


def prune_storage(
    *,
    inputs_dir: Path,
    outputs_dir: Path,
    tasks_dir: Path,
    retention_days: int,
    manifest_max_records: int,
    logger: Any,
) -> dict[str, int]:
    """Prune expired Anima files and compact the input manifest.

    Args:
        inputs_dir: Plugin-owned workspace input directory.
        outputs_dir: Plugin-owned workspace output directory.
        tasks_dir: Per-request task record directory.
        retention_days: File age limit in days. Zero disables age pruning.
        manifest_max_records: Maximum valid manifest records to retain.
        logger: Logger-like object used for non-fatal cleanup warnings.

    Returns:
        Counts of removed files and retained manifest records.
    """
    roots = tuple(Path(path).resolve() for path in (inputs_dir, outputs_dir, tasks_dir))
    cutoff = (
        datetime.now().timestamp()
        - timedelta(days=max(1, retention_days)).total_seconds()
        if retention_days > 0
        else None
    )
    removed_files = 0
    for root in roots:
        if cutoff is None or not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.name in {"manifest.jsonl", "latest.json"}:
                continue
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
                if resolved.stat().st_mtime < cutoff:
                    resolved.unlink()
                    removed_files += 1
            except (OSError, ValueError) as exc:
                logger.warning(
                    "[comfyui_agent] retention cleanup skipped %s: %s",
                    path,
                    exc,
                )
        for directory in sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass

    manifest = Path(inputs_dir) / "manifest.jsonl"
    retained: list[dict[str, Any]] = []
    if manifest.exists():
        try:
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                value = record.get("path") or record.get("relative_path")
                path = Path(str(value or ""))
                if not path.is_absolute():
                    path = manifest.parent.parent / path
                try:
                    path.resolve().relative_to(Path(inputs_dir).resolve())
                except ValueError:
                    continue
                if path.is_file():
                    retained.append(record)
            retained = retained[-max(1, manifest_max_records) :]
            temporary = manifest.with_name(f".{manifest.name}.{uuid.uuid4().hex}.tmp")
            temporary.write_text(
                "".join(
                    json.dumps(record, ensure_ascii=False) + "\n" for record in retained
                ),
                encoding="utf-8",
            )
            os.replace(temporary, manifest)
        except OSError as exc:
            logger.warning(
                "[comfyui_agent] failed to compact input manifest: %s",
                exc,
            )
    return {
        "removed_files": removed_files,
        "manifest_records": len(retained),
    }
