from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import service_container as sc


def test_resolve_service_paths_prefers_plugin_local_tools(tmp_path: Path, monkeypatch):
    root = tmp_path / "root"
    plugin_dir = root / "data" / "plugins" / "astrbot_plugin_anima_master"
    agent_tools = plugin_dir / "agent_tools"
    agent_tools.mkdir(parents=True)
    (agent_tools / "comfyui_agent.py").write_text("", encoding="utf-8")
    (agent_tools / "image_prompt_agent.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(sc, "get_astrbot_root", lambda: str(root))
    monkeypatch.setattr(sc, "__file__", str(plugin_dir / "service_container.py"))

    paths = sc.resolve_service_paths()

    assert paths.root == root
    assert paths.plugin_dir == plugin_dir
    assert paths.tool == agent_tools / "comfyui_agent.py"
    assert paths.prompt_tool == agent_tools / "image_prompt_agent.py"
    assert paths.workspace == root / "workspace"
    assert paths.inputs == root / "workspace" / "inputs"


def test_build_services_returns_key_service_handles(monkeypatch, tmp_path: Path):
    paths = sc.ServicePaths(
        root=tmp_path / "root",
        plugin_dir=tmp_path / "plugin",
        tool=tmp_path / "tool.py",
        prompt_tool=tmp_path / "prompt_tool.py",
        python=tmp_path / "python.exe",
        workspace=tmp_path / "workspace",
        inputs=tmp_path / "workspace" / "inputs",
        plugin_data=tmp_path / "plugin_data",
    )
    monkeypatch.setattr(sc, "resolve_service_paths", lambda: paths)

    class FakeRuntime:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.run_prompt_tool = object()
            self.ensure_ready = object()
            self.run_tool = object()
            self.send_payload = object()

    class FakeTaskRecorder:
        def __init__(self, path, logger):
            self.path = path
            self.logger = logger

    class FakeImageInputs:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.event_image_input = object()

    class FakeReferenceContext:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeMessageContext:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.wants_reference_image = object()
            self.augment_prompt_with_reference_image = object()
            self.augment_prompt_with_quoted_spell = object()
            self.format_spell_payload = object()

    class FakeDanbooruResolver:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakePromptResearcher:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakePromptPipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeGenerationTask:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.generate_payload = object()

    class FakeGenerationVerifier:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeActionHandler:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeBridge:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(sc, "ComfyUIRuntime", FakeRuntime)
    monkeypatch.setattr(sc, "TaskRecorder", FakeTaskRecorder)
    monkeypatch.setattr(sc, "ImageInputResolver", FakeImageInputs)
    monkeypatch.setattr(sc, "ReferenceContextBuilder", FakeReferenceContext)
    monkeypatch.setattr(sc, "MessageContextBuilder", FakeMessageContext)
    monkeypatch.setattr(sc, "DanbooruResolver", FakeDanbooruResolver)
    monkeypatch.setattr(sc, "PromptResearcher", FakePromptResearcher)
    monkeypatch.setattr(sc, "PromptPipeline", FakePromptPipeline)
    monkeypatch.setattr(sc, "GenerationTaskRunner", FakeGenerationTask)
    monkeypatch.setattr(sc, "GenerationVerifier", FakeGenerationVerifier)
    monkeypatch.setattr(sc, "CommandActionHandler", FakeActionHandler)
    monkeypatch.setattr(sc, "LLMToolBridge", FakeBridge)

    services = sc.build_services(
        context=object(),
        config={},
        config_store=None,
        logger=object(),
        danbooru_tag_cache={},
        get_bool=lambda key, default: default,
        get_int=lambda key, default: default,
        get_float=lambda key, default: default,
        get_str=lambda key, default="": default,
        shorten=lambda text, limit: text[:limit],
        is_allowed=lambda event: True,
        build_prompt=object(),
        prompt_summary=lambda: {},
        generate=object(),
        edit=object(),
        remove_bg=object(),
        spell=object(),
        reverse=object(),
    )

    assert isinstance(services.runtime, FakeRuntime)
    assert isinstance(services.task_recorder, FakeTaskRecorder)
    assert isinstance(services.prompt_pipeline, FakePromptPipeline)
    assert isinstance(services.generation_task, FakeGenerationTask)
    assert isinstance(services.generation_verifier, FakeGenerationVerifier)
    assert isinstance(services.action_handler, FakeActionHandler)
    assert isinstance(services.llm_tool_bridge, FakeBridge)
