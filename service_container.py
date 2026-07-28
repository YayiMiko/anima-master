from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot.core.utils.astrbot_path import get_astrbot_root

try:
    from .comfyui_runtime import ComfyUIRuntime
    from .command_actions import CommandActionHandler
    from .danbooru_resolver import DanbooruResolver
    from .generation_task import GenerationTaskRunner
    from .generation_verifier import GenerationVerifier
    from .image_inputs import ImageInputResolver
    from .llm_tool_bridge import LLMToolBridge
    from .message_context import MessageContextBuilder
    from .prompt_pipeline import PromptPipeline
    from .prompt_research import PromptResearcher
    from .reference_context import ReferenceContextBuilder
    from .storage_retention import StorageRetentionManager
    from .task_state import TaskRecorder
except ImportError:  # pragma: no cover - fallback for direct script-style imports.
    from comfyui_runtime import ComfyUIRuntime
    from command_actions import CommandActionHandler
    from danbooru_resolver import DanbooruResolver
    from generation_task import GenerationTaskRunner
    from generation_verifier import GenerationVerifier
    from image_inputs import ImageInputResolver
    from llm_tool_bridge import LLMToolBridge
    from message_context import MessageContextBuilder
    from prompt_pipeline import PromptPipeline
    from prompt_research import PromptResearcher
    from reference_context import ReferenceContextBuilder
    from storage_retention import StorageRetentionManager
    from task_state import TaskRecorder


@dataclass(frozen=True)
class ServicePaths:
    """Resolved filesystem paths used by Anima services.

    Args:
        root: AstrBot root directory.
        plugin_dir: Current plugin directory.
        tool: Main ComfyUI helper script path.
        prompt_tool: Image prompt helper script path.
        python: Preferred Python interpreter path.
        workspace: AstrBot workspace directory.
        inputs: Image input storage directory.
        plugin_data: Plugin persistent data directory.
    """

    root: Path
    plugin_dir: Path
    tool: Path
    prompt_tool: Path
    python: Path
    workspace: Path
    inputs: Path
    plugin_data: Path


@dataclass(frozen=True)
class AnimaServices:
    """Constructed services used by the plugin entry point.

    Args:
        paths: Resolved filesystem paths.
        runtime: Local ComfyUI process/tool runtime.
        task_recorder: Latest task summary recorder.
        image_inputs: Image input resolver.
        reference_context: Image-to-prompt reference context builder.
        message_context: Chat message context builder.
        danbooru_resolver: Danbooru core tag resolver.
        prompt_researcher: Optional prompt research planner.
        prompt_pipeline: Prompt generation pipeline.
        generation_task: Text-to-image task runner.
        action_handler: Chat command action handler.
        llm_tool_bridge: LLM tool bridge.
    """

    paths: ServicePaths
    runtime: ComfyUIRuntime
    task_recorder: TaskRecorder
    image_inputs: ImageInputResolver
    reference_context: ReferenceContextBuilder
    message_context: MessageContextBuilder
    danbooru_resolver: DanbooruResolver
    prompt_researcher: PromptResearcher
    prompt_pipeline: PromptPipeline
    generation_task: GenerationTaskRunner
    generation_verifier: GenerationVerifier
    action_handler: CommandActionHandler
    llm_tool_bridge: LLMToolBridge


def resolve_service_paths() -> ServicePaths:
    """Resolve Anima plugin runtime paths.

    Returns:
        Resolved path bundle for plugin services.
    """
    root = Path(get_astrbot_root())
    plugin_dir = Path(__file__).resolve().parent
    tool = plugin_dir / "agent_tools" / "comfyui_agent.py"
    prompt_tool = plugin_dir / "agent_tools" / "image_prompt_agent.py"
    if not tool.exists():
        tool = root / "agent_tools" / "comfyui_agent.py"
    if not prompt_tool.exists():
        prompt_tool = root / "agent_tools" / "image_prompt_agent.py"
    workspace = root / "workspace"
    return ServicePaths(
        root=root,
        plugin_dir=plugin_dir,
        tool=tool,
        prompt_tool=prompt_tool,
        python=root / ".venv" / "Scripts" / "python.exe",
        workspace=workspace,
        inputs=workspace / "inputs",
        plugin_data=root / "data" / "plugin_data" / "astrbot_plugin_anima_master",
    )


def build_services(
    *,
    context: Any,
    config: dict[str, Any],
    config_store: Any = None,
    logger: Any,
    danbooru_tag_cache: dict[str, Any],
    get_bool: Callable[[str, bool], bool],
    get_int: Callable[[str, int], int],
    get_float: Callable[[str, float], float],
    get_str: Callable[[str, str], str],
    shorten: Callable[[str, int], str],
    is_allowed: Callable[[Any], bool],
    build_prompt: Callable[..., Any],
    prompt_summary: Callable[[], dict[str, Any]],
    generate: Callable[..., Any],
    edit: Callable[[Any, str], Any],
    remove_bg: Callable[[Any], Any],
    spell: Callable[[Any], Any],
    reverse: Callable[[Any], Any],
) -> AnimaServices:
    """Build all Anima services for the plugin entry point.

    Args:
        context: AstrBot plugin context.
        config: Plugin configuration dict.
        config_store: Original mutable plugin config object, when available.
        logger: Logger compatible with AstrBot logger methods.
        danbooru_tag_cache: Shared Danbooru lookup cache.
        get_bool: Config boolean accessor.
        get_int: Config integer accessor.
        get_float: Config float accessor.
        get_str: Config string accessor.
        shorten: Text-shortening helper.
        is_allowed: Permission checker.
        build_prompt: Prompt builder callback.
        prompt_summary: Latest prompt summary callback.
        generate: Generation callback for LLM tools and commands.
        edit: Edit callback for LLM tools.
        remove_bg: Remove-background callback for LLM tools.
        spell: Spell extraction callback for LLM tools.
        reverse: Reverse prompt callback for LLM tools.

    Returns:
        Constructed service container.
    """
    paths = resolve_service_paths()
    retention = StorageRetentionManager(
        inputs_dir=paths.inputs,
        outputs_dir=paths.workspace / "outputs",
        tasks_dir=paths.plugin_data / "tasks",
        retention_days=max(0, get_int("storage_retention_days", 30)),
        manifest_max_records=max(1, get_int("manifest_max_records", 5000)),
        logger=logger,
    )
    retention.run(force=True)
    runtime = ComfyUIRuntime(
        root=paths.root,
        tool=paths.tool,
        prompt_tool=paths.prompt_tool,
        python=paths.python,
        config=config,
        logger=logger,
        get_bool=get_bool,
        get_int=get_int,
        get_str=get_str,
    )
    task_recorder = TaskRecorder(paths.plugin_data / "last_task.json", logger)
    image_inputs = ImageInputResolver(
        workspace=paths.workspace,
        inputs_dir=paths.inputs,
        logger=logger,
        shorten=shorten,
    )
    reference_context = ReferenceContextBuilder(
        context=context,
        run_prompt_tool=runtime.run_prompt_tool,
        event_image_input=image_inputs.event_image_input,
        logger=logger,
        get_int=get_int,
        shorten=shorten,
    )
    message_context = MessageContextBuilder(
        reference_context=reference_context,
        event_image_input=image_inputs.event_image_input,
        logger=logger,
        get_bool=get_bool,
        shorten=shorten,
    )
    danbooru_resolver = DanbooruResolver(
        logger=logger,
        cache=danbooru_tag_cache,
        get_bool=get_bool,
        get_int=get_int,
        get_float=get_float,
        get_str=get_str,
    )
    prompt_researcher = PromptResearcher(
        context=context,
        logger=logger,
        get_bool=get_bool,
        get_int=get_int,
        get_str=get_str,
    )
    prompt_pipeline = PromptPipeline(
        context=context,
        config=config,
        logger=logger,
        danbooru_resolver=danbooru_resolver,
        researcher=prompt_researcher,
        get_bool=get_bool,
        get_int=get_int,
        get_float=get_float,
        get_str=get_str,
        shorten=shorten,
    )
    generation_task = GenerationTaskRunner(
        task_recorder=task_recorder,
        image_inputs=image_inputs,
        reference_context=reference_context,
        is_allowed=is_allowed,
        ensure_ready=runtime.ensure_ready,
        wants_reference_image=message_context.wants_reference_image,
        augment_reference_image=message_context.augment_prompt_with_reference_image,
        augment_quoted_spell=message_context.augment_prompt_with_quoted_spell,
        build_prompt=build_prompt,
        prompt_summary=prompt_summary,
        run_tool=runtime.run_tool,
        get_bool=get_bool,
        get_int=get_int,
        get_float=get_float,
        get_str=get_str,
        shorten=shorten,
        maintenance=retention.run,
    )
    action_handler = CommandActionHandler(
        config=config,
        config_store=config_store,
        task_recorder=task_recorder,
        reference_context=reference_context,
        is_allowed=is_allowed,
        run_tool=runtime.run_tool,
        ensure_ready=runtime.ensure_ready,
        send_payload=runtime.send_payload,
        generate=generate,
        event_image_input=image_inputs.event_image_input,
        image_input_summary=lambda: dict(image_inputs.last_summary),
        build_prompt=build_prompt,
        format_spell_payload=message_context.format_spell_payload,
        get_bool=get_bool,
        shorten=shorten,
    )
    generation_verifier = GenerationVerifier(
        context=context,
        task_recorder=task_recorder,
        generate_payload=generation_task.generate_payload,
        logger=logger,
        get_bool=get_bool,
        get_int=get_int,
        get_str=get_str,
    )
    llm_tool_bridge = LLMToolBridge(
        run_tool=runtime.run_tool,
        generate=generate,
        edit=edit,
        remove_bg=remove_bg,
        spell=spell,
        reverse=reverse,
    )
    return AnimaServices(
        paths=paths,
        runtime=runtime,
        task_recorder=task_recorder,
        image_inputs=image_inputs,
        reference_context=reference_context,
        message_context=message_context,
        danbooru_resolver=danbooru_resolver,
        prompt_researcher=prompt_researcher,
        prompt_pipeline=prompt_pipeline,
        generation_task=generation_task,
        generation_verifier=generation_verifier,
        action_handler=action_handler,
        llm_tool_bridge=llm_tool_bridge,
    )
