import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

try:
    from .config_view import build_config_debug_lines
    from .task_summary import build_last_task_debug_lines
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from config_view import build_config_debug_lines
    from task_summary import build_last_task_debug_lines


class TaskRecorder:
    """Persist and render non-secret Anima task state."""

    def __init__(self, path: Path, logger: Any):
        """Create a task recorder.

        Args:
            path: Destination path for the latest task JSON.
            logger: Logger-like object used for warning messages.
        """
        self.path = Path(path)
        self._logger = logger

    def write(self, task: dict[str, Any]) -> None:
        """Persist a non-secret summary for the latest Anima task.

        Args:
            task: Summary fields for the task. Values must avoid API keys,
                cookies, account tokens, and other secrets.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(task, ensure_ascii=False, indent=2)
            # Atomic write: dump into a same-directory tempfile, fsync, then
            # os.replace onto the target. os.replace is atomic on both POSIX
            # and Windows, so a concurrent writer or crash can never leave
            # last_task.json half-written.
            fd, tmp_path = tempfile.mkstemp(
                prefix=self.path.name + ".",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                # Windows quirk: os.replace fails with PermissionError if the
                # target is currently opened by another process (e.g. a reader
                # via read_text()). Retry a few times with a tiny backoff so
                # occasional read/write collisions don't drop the update.
                last_exc: Exception | None = None
                for attempt in range(5):
                    try:
                        os.replace(tmp_path, self.path)
                        last_exc = None
                        break
                    except PermissionError as exc:
                        last_exc = exc
                        time.sleep(0.02 * (attempt + 1))
                if last_exc is not None:
                    raise last_exc
            except Exception:
                # Clean up the stray tempfile on any mid-write failure.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as exc:
            self._logger.warning("[comfyui_agent] failed to write last task summary: %s", exc)

    def read(self) -> dict[str, Any]:
        """Read the latest non-secret Anima task summary.

        Returns:
            The latest task summary, or an empty dict when the file is missing
            or unreadable.
        """
        try:
            if not self.path.exists():
                return {}
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            self._logger.warning("[comfyui_agent] failed to read last task summary: %s", exc)
            return {}

    def debug_status_text(self, config: dict[str, Any]) -> str:
        """Build a non-secret debug summary for chat-side inspection.

        Args:
            config: Current plugin configuration.

        Returns:
            A compact text summary of key Anima plugin settings and the latest
            task record path.
        """
        last_task = self.read()
        lines = build_config_debug_lines(
            config,
            task_path=self.path,
            task_exists=self.path.exists(),
        )
        if last_task:
            lines.extend(build_last_task_debug_lines(last_task))
        return "\n".join(lines)
