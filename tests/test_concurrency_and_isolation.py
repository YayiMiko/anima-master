from __future__ import annotations

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = PLUGIN_DIR / "agent_tools"
for import_path in (PLUGIN_DIR, TOOLS_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from comfyui_history import ComfyUIHistoryRunner  # noqa: E402
from command_actions import CommandActionHandler  # noqa: E402
import comfyui_runtime as runtime_module  # noqa: E402
from comfyui_runtime import ComfyUIRuntime  # noqa: E402
from generation_task import GenerationTaskRunner  # noqa: E402
from image_manifest import ImageInputManifest  # noqa: E402
from task_state import TaskRecorder  # noqa: E402


class _Logger:
    def warning(self, *args) -> None:
        pass


class _Event:
    unified_msg_origin = "test"

    def get_platform_id(self) -> str:
        return "test"

    def get_session_id(self) -> str:
        return "session"

    def get_sender_id(self) -> str:
        return "sender"


def test_chat_image_actions_never_fall_back_to_global_latest() -> None:
    tool_calls: list[list[str]] = []

    async def run_tool(args: list[str]) -> dict:
        tool_calls.append(args)
        return {"ok": True}

    async def no_image(_event) -> None:
        return None

    handler = CommandActionHandler(
        config={"img2img_enabled": True},
        task_recorder=object(),
        reference_context=object(),
        is_allowed=lambda _event: True,
        run_tool=run_tool,
        ensure_ready=lambda _event: asyncio.sleep(0, result={"ok": True}),
        send_payload=lambda _event, _payload: asyncio.sleep(0, result="ok"),
        generate=lambda *_args, **_kwargs: asyncio.sleep(0),
        event_image_input=no_image,
        build_prompt=lambda *_args, **_kwargs: asyncio.sleep(0, result="prompt"),
        format_spell_payload=lambda _payload: "",
        get_bool=lambda key, default: True if key == "img2img_enabled" else default,
        shorten=lambda text, limit: text[:limit],
    )

    edit_result = asyncio.run(handler.edit(_Event(), "修改衣服"))
    upscale_result = asyncio.run(handler.upscale(_Event()))

    assert "请在本次消息中附图" in edit_result
    assert "请在本次消息中附图" in upscale_result
    assert tool_calls == []


def test_delivery_updates_its_originating_task_only(tmp_path: Path) -> None:
    recorder = TaskRecorder(tmp_path / "last_task.json", _Logger())
    older = recorder.build_generation_start(
        event=_Event(),
        started_at=datetime.fromisoformat("2026-07-28T10:00:00.000001"),
        original_prompt="A",
        reference_requested=False,
        width=1024,
        height=1536,
        explicit_size=False,
        steps=30,
        cfg=5.0,
        workflow="anima_t2i",
        shorten=lambda text, limit: text[:limit],
    )
    newer = recorder.build_generation_start(
        event=_Event(),
        started_at=datetime.fromisoformat("2026-07-28T10:00:00.000001"),
        original_prompt="B",
        reference_requested=False,
        width=1024,
        height=1536,
        explicit_size=False,
        steps=30,
        cfg=5.0,
        workflow="anima_t2i",
        shorten=lambda text, limit: text[:limit],
    )
    recorder.write(older)
    recorder.write(newer)

    runner = GenerationTaskRunner.__new__(GenerationTaskRunner)
    runner._task_recorder = recorder
    runner.record_delivery(older["task_id"], {"status": "sent"})

    assert recorder.read(older["task_id"])["delivery"]["status"] == "sent"
    assert "delivery" not in recorder.read(newer["task_id"])
    assert recorder.read()["task_id"] == newer["task_id"]


def test_task_writes_remain_valid_json_under_concurrency(tmp_path: Path) -> None:
    recorder = TaskRecorder(tmp_path / "last_task.json", _Logger())
    tasks = []
    for index in range(20):
        task = recorder.build_generation_start(
            event=_Event(),
            started_at=datetime.fromisoformat(f"2026-07-28T10:00:00.{index:06d}"),
            original_prompt=str(index),
            reference_requested=False,
            width=1024,
            height=1536,
            explicit_size=False,
            steps=30,
            cfg=5.0,
            workflow="anima_t2i",
            shorten=lambda text, limit: text[:limit],
        )
        tasks.append(task)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(recorder.write, tasks))

    json.loads((tmp_path / "last_task.json").read_text(encoding="utf-8"))
    assert len(list((tmp_path / "tasks").glob("*.json"))) == len(tasks)
    for task in tasks:
        assert recorder.read(task["task_id"])["task_id"] == task["task_id"]


def test_manifest_appends_remain_complete_under_concurrency(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    inputs = workspace / "inputs"
    manifest = ImageInputManifest(workspace=workspace, inputs_dir=inputs)
    event = _Event()
    targets = []
    for index in range(20):
        target = inputs / "20260728" / "session" / f"{index}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"image")
        targets.append(target)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda target: manifest.write_input_record(
                    event,
                    target,
                    target.name,
                ),
                targets,
            )
        )

    lines = (inputs / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == len(targets)
    json.loads(
        (inputs / "20260728" / "session" / "latest.json").read_text(encoding="utf-8")
    )


def test_input_directories_isolate_senders_in_the_same_session(
    tmp_path: Path,
) -> None:
    class _OtherSender(_Event):
        def get_sender_id(self) -> str:
            return "other"

    manifest = ImageInputManifest(
        workspace=tmp_path / "workspace",
        inputs_dir=tmp_path / "workspace" / "inputs",
    )

    first = manifest.input_target_dir(_Event())
    second = manifest.input_target_dir(_OtherSender())

    assert first != second
    assert first.name == "sender"
    assert second.name == "other"


def test_output_names_are_unique(tmp_path: Path) -> None:
    runner = ComfyUIHistoryRunner.__new__(ComfyUIHistoryRunner)
    runner.image_outputs = tmp_path
    runner.client = type(
        "_Client",
        (),
        {"view_image_bytes": lambda self, image, timeout: b"image"},
    )()

    outputs = [runner.download_image({"filename": "result.png"}, 1) for _ in range(20)]

    assert len(set(outputs)) == len(outputs)
    assert all(path.read_bytes() == b"image" for path in outputs)


def test_image_send_failure_emits_plain_text_notice(tmp_path: Path) -> None:
    output = tmp_path / "result.png"
    output.write_bytes(b"image")

    class _SendEvent:
        def __init__(self) -> None:
            self.sent: list[tuple[str, str]] = []

        def chain_result(self, _chain) -> tuple[str, str]:
            return ("image", "")

        def plain_result(self, text: str) -> tuple[str, str]:
            return ("plain", text)

        async def send(self, result: tuple[str, str]) -> None:
            self.sent.append(result)
            if result[0] == "image":
                raise RuntimeError("platform rejected image")

    runtime = ComfyUIRuntime.__new__(ComfyUIRuntime)
    runtime._bool = lambda _key, default: default
    runtime._int = lambda _key, default: default
    runtime.logger = _Logger()
    event = _SendEvent()
    payload = {"ok": True, "outputs": [str(output)]}

    asyncio.run(runtime.send_payload(event, payload))

    assert [kind for kind, _text in event.sent] == ["image", "plain"]
    assert "发送失败" in event.sent[-1][1]
    assert payload["delivery"]["status"] == "send_failed"


def test_image_ack_timeout_is_recorded_without_chat_notice(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "result.png"
    output.write_bytes(b"image")

    class _ActionFailed(Exception):
        retcode = 1200

    class _SendEvent:
        def __init__(self) -> None:
            self.sent: list[tuple[str, str]] = []

        def chain_result(self, _chain) -> tuple[str, str]:
            return ("image", "")

        def plain_result(self, text: str) -> tuple[str, str]:
            return ("plain", text)

        async def send(self, result: tuple[str, str]) -> None:
            self.sent.append(result)
            if result[0] == "image":
                raise _ActionFailed("Timeout")

    monkeypatch.setattr(runtime_module, "ActionFailed", _ActionFailed)
    runtime = ComfyUIRuntime.__new__(ComfyUIRuntime)
    runtime._bool = lambda _key, default: default
    runtime._int = lambda _key, default: default
    runtime.logger = _Logger()
    event = _SendEvent()
    payload = {"ok": True, "outputs": [str(output)]}

    asyncio.run(runtime.send_payload(event, payload))

    assert [kind for kind, _text in event.sent] == ["image"]
    assert payload["delivery"]["status"] == "delivery_uncertain"
    assert payload["delivery"]["sent"] is None
    assert payload["delivery"]["notice_suppressed"] is True


def test_delivery_sends_the_verifier_selected_output_first(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first = tmp_path / "first.png"
    selected = tmp_path / "selected.png"
    first.write_bytes(b"first")
    selected.write_bytes(b"selected")

    class _SendEvent:
        def __init__(self) -> None:
            self.sent: list[str] = []

        def chain_result(self, chain):
            return chain[0]

        async def send(self, result: str) -> None:
            self.sent.append(result)

    monkeypatch.setattr(
        runtime_module.Comp.Image,
        "fromFileSystem",
        staticmethod(lambda path: path),
    )
    runtime = ComfyUIRuntime.__new__(ComfyUIRuntime)
    runtime._bool = lambda _key, default: default
    runtime._int = lambda _key, default: default
    runtime.logger = _Logger()
    event = _SendEvent()
    payload = {
        "ok": True,
        "outputs": [str(first), str(selected)],
        "selected_output_path": str(selected),
    }

    asyncio.run(runtime.send_payload(event, payload))

    assert event.sent == [str(selected)]
