from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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
    from .task_state import TaskRecorder
except Exception:  # pragma: no cover - fallback for direct script-style imports.
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
        generation_verifier: Post-generation verifier and retry runner.
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


@dataclass(frozen=True)
class RuntimeServices:
    """Low-level runtime and image-context services."""

    runtime: ComfyUIRuntime
    task_recorder: TaskRecorder
    image_inputs: ImageInputResolver
    reference_context: ReferenceContextBuilder
    message_context: MessageContextBuilder


@dataclass(frozen=True)
class PromptServices:
    """Prompt-building and research services."""

    danbooru_resolver: DanbooruResolver
    prompt_researcher: PromptResearcher
    prompt_pipeline: PromptPipeline


@dataclass(frozen=True)
class TaskServices:
    """Task execution services for generation and verification."""

    generation_task: GenerationTaskRunner
    generation_verifier: GenerationVerifier


@dataclass(frozen=True)
class CommandServices:
    """Chat command and LLM tool bridge services."""

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


def build_runtime_services(
    *,
    paths: ServicePaths,
    context: Any,
    config: dict[str, Any],
    logger: Any,
    get_bool: Callable[[str, bool], bool],
    get_int: Callable[[str, int], int],
    get_str: Callable[[str, str], str],
    shorten: Callable[[str, int], str],
) -> RuntimeServices:
    """Build low-level runtime and image-context services."""
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
    return RuntimeServices(
        runtime=runtime,
        task_recorder=task_recorder,
        image_inputs=image_inputs,
        reference_context=reference_context,
        message_context=message_context,
    )


def build_prompt_services(
    *,
    context: Any,
    config: dict[str, Any],
    logger: Any,
    danbooru_tag_cache: dict[str, list[Any]],
    get_bool: Callable[[str, bool], bool],
    get_int: Callable[[str, int], int],
    get_float: Callable[[str, float], float],
    get_str: Callable[[str, str], str],
    shorten: Callable[[str, int], str],
) -> PromptServices:
    """Build prompt, research, and resolver services."""
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
    return PromptServices(
        danbooru_resolver=danbooru_resolver,
        prompt_researcher=prompt_researcher,
        prompt_pipeline=prompt_pipeline,
    )


def build_task_services(
    *,
    context: Any,
    config: dict[str, Any],
    logger: Any,
    runtime_services: RuntimeServices,
    build_prompt: Callable[..., Any],
    prompt_summary: Callable[[], dict[str, Any]],
    is_allowed: Callable[[Any], bool],
    get_bool: Callable[[str, bool], bool],
    get_int: Callable[[str, int], int],
    get_float: Callable[[str, float], float],
    get_str: Callable[[str, str], str],
    shorten: Callable[[str, int], str],
) -> TaskServices:
    """Build generation and verification task services."""
    generation_task = GenerationTaskRunner(
        task_recorder=runtime_services.task_recorder,
        image_inputs=runtime_services.image_inputs,
        reference_context=runtime_services.reference_context,
        is_allowed=is_allowed,
        ensure_ready=runtime_services.runtime.ensure_ready,
        wants_reference_image=runtime_services.message_context.wants_reference_image,
        augment_reference_image=runtime_services.message_context.augment_prompt_with_reference_image,
        augment_quoted_spell=runtime_services.message_context.augment_prompt_with_quoted_spell,
        build_prompt=build_prompt,
        prompt_summary=prompt_summary,
        run_tool=runtime_services.runtime.run_tool,
        get_bool=get_bool,
        get_int=get_int,
        get_float=get_float,
        get_str=get_str,
        shorten=shorten,
    )
    generation_verifier = GenerationVerifier(
        context=context,
        task_recorder=runtime_services.task_recorder,
        generate_payload=generation_task.generate_payload,
        logger=logger,
        get_bool=get_bool,
        get_int=get_int,
        get_str=get_str,
    )
    return TaskServices(
        generation_task=generation_task,
        generation_verifier=generation_verifier,
    )


def build_command_services(
    *,
    config: dict[str, Any],
    config_store: Any,
    runtime_services: RuntimeServices,
    is_allowed: Callable[[Any], bool],
    generate: Callable[..., Any],
    edit: Callable[[Any, str], Any],
    remove_bg: Callable[[Any], Any],
    spell: Callable[[Any], Any],
    reverse: Callable[[Any], Any],
    build_prompt: Callable[..., Any],
    get_bool: Callable[[str, bool], bool],
    shorten: Callable[[str, int], str],
) -> CommandServices:
    """Build chat command and LLM tool bridge services."""
    action_handler = CommandActionHandler(
        config=config,
        config_store=config_store,
        task_recorder=runtime_services.task_recorder,
        reference_context=runtime_services.reference_context,
        is_allowed=is_allowed,
        run_tool=runtime_services.runtime.run_tool,
        ensure_ready=runtime_services.runtime.ensure_ready,
        send_payload=runtime_services.runtime.send_payload,
        generate=generate,
        event_image_input=runtime_services.image_inputs.event_image_input,
        build_prompt=build_prompt,
        format_spell_payload=runtime_services.message_context.format_spell_payload,
        get_bool=get_bool,
        shorten=shorten,
    )
    llm_tool_bridge = LLMToolBridge(
        run_tool=runtime_services.runtime.run_tool,
        generate=generate,
        edit=edit,
        remove_bg=remove_bg,
        spell=spell,
        reverse=reverse,
    )
    return CommandServices(
        action_handler=action_handler,
        llm_tool_bridge=llm_tool_bridge,
    )


def build_services(
    *,
    context: Any,
    config: dict[str, Any],
    config_store: Any = None,
    logger: Any,
    danbooru_tag_cache: dict[str, list[Any]],
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
    runtime_services = build_runtime_services(
        paths=paths,
        context=context,
        config=config,
        logger=logger,
        get_bool=get_bool,
        get_int=get_int,
        get_str=get_str,
        shorten=shorten,
    )
    prompt_services = build_prompt_services(
        context=context,
        config=config,
        logger=logger,
        danbooru_tag_cache=danbooru_tag_cache,
        get_bool=get_bool,
        get_int=get_int,
        get_float=get_float,
        get_str=get_str,
        shorten=shorten,
    )
    task_services = build_task_services(
        context=context,
        config=config,
        logger=logger,
        runtime_services=runtime_services,
        build_prompt=build_prompt,
        prompt_summary=prompt_summary,
        is_allowed=is_allowed,
        get_bool=get_bool,
        get_int=get_int,
        get_float=get_float,
        get_str=get_str,
        shorten=shorten,
    )
    command_services = build_command_services(
        config=config,
        config_store=config_store,
        runtime_services=runtime_services,
        is_allowed=is_allowed,
        generate=generate,
        edit=edit,
        remove_bg=remove_bg,
        spell=spell,
        reverse=reverse,
        build_prompt=build_prompt,
        get_bool=get_bool,
        shorten=shorten,
    )
    return AnimaServices(
        paths=paths,
        runtime=runtime_services.runtime,
        task_recorder=runtime_services.task_recorder,
        image_inputs=runtime_services.image_inputs,
        reference_context=runtime_services.reference_context,
        message_context=runtime_services.message_context,
        danbooru_resolver=prompt_services.danbooru_resolver,
        prompt_researcher=prompt_services.prompt_researcher,
        prompt_pipeline=prompt_services.prompt_pipeline,
        generation_task=task_services.generation_task,
        generation_verifier=task_services.generation_verifier,
        action_handler=command_services.action_handler,
        llm_tool_bridge=command_services.llm_tool_bridge,
    )
