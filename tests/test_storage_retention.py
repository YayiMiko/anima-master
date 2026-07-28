from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from storage_retention import StorageRetentionManager, prune_storage  # noqa: E402


class _Logger:
    def warning(self, *args) -> None:
        pass


def test_prune_storage_removes_only_expired_scoped_files_and_compacts_manifest(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    inputs = workspace / "inputs"
    outputs = workspace / "outputs"
    tasks = tmp_path / "plugin_data" / "tasks"
    for directory in (inputs, outputs, tasks):
        directory.mkdir(parents=True)
    old_input = inputs / "old.png"
    live_input = inputs / "live.png"
    old_output = outputs / "old.png"
    old_task = tasks / "old.json"
    outside = tmp_path / "outside.png"
    for path in (old_input, live_input, old_output, old_task, outside):
        path.write_bytes(b"x")
    old_timestamp = (datetime.now() - timedelta(days=60)).timestamp()
    for path in (old_input, old_output, old_task, outside):
        os.utime(path, (old_timestamp, old_timestamp))

    manifest = inputs / "manifest.jsonl"
    manifest.write_text(
        "\n".join(
            [
                "{broken",
                json.dumps({"kind": "image", "path": str(old_input)}),
                json.dumps({"kind": "image", "path": str(live_input)}),
                json.dumps({"kind": "image", "path": str(outside)}),
            ]
        ),
        encoding="utf-8",
    )

    result = prune_storage(
        inputs_dir=inputs,
        outputs_dir=outputs,
        tasks_dir=tasks,
        retention_days=30,
        manifest_max_records=10,
        logger=_Logger(),
    )

    assert result == {"removed_files": 3, "manifest_records": 1}
    assert live_input.exists()
    assert outside.exists()
    records = [
        json.loads(line)
        for line in manifest.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [{"kind": "image", "path": str(live_input)}]


def test_retention_manager_runs_periodically(tmp_path: Path) -> None:
    manager = StorageRetentionManager(
        inputs_dir=tmp_path / "inputs",
        outputs_dir=tmp_path / "outputs",
        tasks_dir=tmp_path / "tasks",
        retention_days=30,
        manifest_max_records=10,
        logger=_Logger(),
        interval=2,
    )

    assert manager.run() is None
    assert manager.run() == {"removed_files": 0, "manifest_records": 0}
