from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from anima.prompts.multi_person_prompt import (  # noqa: E402
    build_multi_person_plan_prompt,
    parse_multi_person_plan,
)
from anima.prompts.danbooru_resolver import DanbooruResolveOutcome  # noqa: E402
from anima.prompts.prompt_background import (  # noqa: E402
    DEFAULT_PORTRAIT,
    EXPLICIT_SCENE,
    apply_default_portrait_tags,
    extract_background_mode,
)
from anima.prompts.prompt_builder import build_final_prompt  # noqa: E402
from anima.prompts.prompt_pipeline import PromptPipeline  # noqa: E402
from anima.prompts.prompt_templates import build_llm_prompt  # noqa: E402


def test_background_marker_is_removed_before_tag_processing() -> None:
    tags, mode = extract_background_mode(
        "1girl, white dress, simple background, background_mode_default_portrait"
    )

    assert mode == DEFAULT_PORTRAIT
    assert tags == "1girl, white dress, simple background"

    tags, mode = extract_background_mode(
        "1girl, beach, sunset, background_mode_explicit_scene"
    )

    assert mode == EXPLICIT_SCENE
    assert "background_mode" not in tags


def test_default_portrait_adds_white_background_without_overriding_closeup() -> None:
    assert apply_default_portrait_tags("1girl, white dress") == (
        "1girl, white dress, full body, centered, simple background, white background"
    )
    closeup = apply_default_portrait_tags("1girl, close-up, smile")
    assert "full body" not in closeup
    assert "simple background" in closeup
    assert "white background" in closeup


def test_final_prompt_enforces_default_portrait_but_preserves_explicit_scene() -> None:
    config = {
        "chiyo_preset_enabled": False,
        "quality_prefix": "",
        "default_artist_tags": "",
        "style_tags": "",
    }
    default_result = build_final_prompt(
        user_prompt="白裙女孩",
        llm_content="1girl, white dress",
        config=config,
        background_mode=DEFAULT_PORTRAIT,
    )
    explicit_result = build_final_prompt(
        user_prompt="海边的白裙女孩",
        llm_content="1girl, white dress, beach, sunset",
        config=config,
        background_mode=EXPLICIT_SCENE,
    )

    assert "simple background" in default_result.content_tags
    assert "white background" in default_result.content_tags
    assert "full body" in default_result.content_tags
    assert "white background" not in explicit_result.content_tags
    assert "beach" in explicit_result.content_tags


def test_custom_template_still_receives_mandatory_llm_background_protocol() -> None:
    prompt = build_llm_prompt(
        "参考图视觉反推 tags：bedroom\n画狐莉穿这套衣服",
        prompt_builder_template="自定义规则：{theme}",
        original_theme="画狐莉穿这套衣服",
    )

    assert "自定义规则" in prompt
    assert "background_mode_default_portrait" in prompt
    assert "background_mode_explicit_scene" in prompt
    assert "用户原始文字：\n画狐莉穿这套衣服" in prompt


def test_multi_person_plan_uses_llm_background_mode_and_original_text() -> None:
    prompt = build_multi_person_plan_prompt(
        "参考图视觉反推 tags：classroom\n狐莉和团子牵手",
        original_user_prompt="狐莉和团子牵手",
    )

    assert "Original user text for background intent:\n狐莉和团子牵手" in prompt
    assert "Expanded request for all other visual details" in prompt

    plan = parse_multi_person_plan(
        """{
          "count_tags": ["2girls"],
          "common_tags": ["full body"],
          "characters": [{"name": "A"}, {"name": "B"}],
          "interactions": ["Character A holds Character B's hand."],
          "spatial_mode": "shared_contact",
          "background_mode": "default_portrait",
          "composition": "One unified view."
        }"""
    )

    assert plan is not None
    assert plan.background_mode == DEFAULT_PORTRAIT


def test_missing_background_marker_asks_llm_again_before_adding_white() -> None:
    class Context:
        def __init__(self, marker: str):
            self.marker = marker
            self.calls = []

        async def get_current_chat_provider_id(self, umo):
            return "provider"

        async def llm_generate(self, **kwargs):
            self.calls.append(kwargs)
            content = "1girl, beach, sunset" if len(self.calls) == 1 else self.marker
            return type("Response", (), {"completion_text": content})()

    class Resolver:
        def required_core_tags_for_prompt(self, prompt):
            return ()

        async def resolve_detailed(self, *, llm_content, **kwargs):
            return DanbooruResolveOutcome(text=llm_content)

    class Researcher:
        def plan(self, prompt):
            return type(
                "Plan",
                (),
                {
                    "use_web_search": False,
                    "use_deep_thinking": False,
                    "search_reason": "",
                    "thinking_reason": "",
                },
            )()

    class Logger:
        def info(self, *args):
            pass

        def warning(self, *args):
            pass

    async def build(marker: str):
        context = Context(marker)
        config = {"chiyo_preset_enabled": False}
        pipeline = PromptPipeline(
            context=context,
            config=config,
            logger=Logger(),
            danbooru_resolver=Resolver(),
            researcher=Researcher(),
            get_bool=lambda key, default: bool(config.get(key, default)),
            get_int=lambda key, default: int(config.get(key, default)),
            get_float=lambda key, default: float(config.get(key, default)),
            get_str=lambda key, default: str(config.get(key, default)),
            shorten=lambda text, limit: text[:limit],
        )
        event = type("Event", (), {"unified_msg_origin": "session"})()
        return await pipeline.build(event, "海边日落的女孩"), context.calls

    result, calls = asyncio.run(build("background_mode_explicit_scene"))
    assert len(calls) == 2
    assert result.summary["background_mode_source"] == "llm_fallback"
    assert "white background" not in result.final_prompt

    result, _ = asyncio.run(build("unexpected output"))
    assert result.summary["background_mode"] == "unresolved"
    assert "white background" not in result.final_prompt
