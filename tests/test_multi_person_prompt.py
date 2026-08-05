from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from danbooru_resolver import DanbooruResolveOutcome  # noqa: E402
from multi_person_prompt import (  # noqa: E402
    MultiPersonCharacter,
    build_multi_person_plan_prompt,
    parse_multi_person_plan,
    render_multi_person_character,
)
from prompt_pipeline import PromptPipeline  # noqa: E402


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class _Plan:
    use_web_search = False
    use_deep_thinking = False
    search_reason = ""
    thinking_reason = ""


class _Researcher:
    def plan(self, prompt):
        return _Plan()


class _Response:
    def __init__(self, text: str):
        self.completion_text = text


class _Event:
    unified_msg_origin = "session"


def _plan_json(*, conflicting_fixed_appearance: bool = False) -> str:
    return json.dumps(
        {
            "count_tags": ["2girls"],
            "common_tags": ["wide shot", "full body", "autumn street"],
            "characters": [
                {
                    "slot": "left",
                    "role": "calm guitarist",
                    "visual_label": "green-eyed guitarist",
                    "identity_anchors": ["green eyes"],
                    "emphasized_anchors": ["green eyes"],
                    "name": "若叶睦",
                    "danbooru_candidate": "mutsumi_wakaba",
                    "appearance": (
                        "orange hair" if conflicting_fixed_appearance else "green eyes"
                    ),
                    "clothing": "dark school uniform",
                    "expression": "calm expression",
                    "pose": "walking forward",
                    "props": ["guitar case"],
                },
                {
                    "slot": "right",
                    "role": "cheerful friend",
                    "visual_label": "pink-haired friend",
                    "identity_anchors": ["pink hair"],
                    "name": "千早爱音",
                    "danbooru_candidate": "anon_chihaya",
                    "appearance": "pink hair",
                    "clothing": "pink jacket",
                    "expression": "cheerful smile",
                    "pose": "walking forward",
                    "props": [],
                },
            ],
            "interactions": [
                "Character B is holding Character A's hand.",
                "A second competing action that must be discarded.",
            ],
            "relationship_tag": "holding hands",
            "composition": "Both characters appear once in one continuous scene.",
        },
        ensure_ascii=False,
    )


def test_multi_person_plan_parser_requires_two_to_four_characters() -> None:
    plan = parse_multi_person_plan(_plan_json())

    assert plan is not None
    assert plan.interactions == ("Character B is holding Character A's hand.",)
    invalid = json.dumps(
        {
            "count_tags": ["1girl"],
            "characters": [
                {
                    "slot": "left",
                    "name": "若叶睦",
                    "appearance": "green eyes",
                }
            ],
        }
    )
    assert parse_multi_person_plan(invalid) is None


def test_multi_person_parser_replaces_panel_like_slots_and_composition() -> None:
    data = json.loads(_plan_json())
    data["characters"][0]["slot"] = "top_left"
    data["characters"][1]["slot"] = "bottom_right"
    data["composition"] = "A split screen with two comic panels."

    plan = parse_multi_person_plan(json.dumps(data))

    assert plan is not None
    assert tuple(character.slot for character in plan.characters) == (
        "left",
        "right",
    )
    assert plan.composition == ""


def test_character_renderer_uses_fixed_tags_as_authoritative_identity() -> None:
    block = render_multi_person_character(
        MultiPersonCharacter(
            slot="left",
            name="狐莉",
            danbooru_candidate="wrong_guessed_name",
            appearance="orange hair, blue eyes",
            clothing="black dress",
            expression="smiling",
            pose="standing",
            props=("dango",),
        ),
        alias="Character A",
        fixed_tags="white hair, red eyes, fox ears",
    )

    assert block.startswith("Character A:")
    assert "wrong_guessed_name" not in block
    assert "On the left" not in block
    assert "white hair, red eyes, fox ears" in block
    assert "orange hair" not in block
    assert "black dress" in block


def test_plan_prompt_marks_fixed_character_tags_as_authoritative() -> None:
    prompt = build_multi_person_plan_prompt(
        "狐莉牵着格林的手",
        fixed_characters={"狐莉": "white hair, red eyes, fox ears"},
    )

    assert '"狐莉": "white hair, red eyes, fox ears"' in prompt
    assert 'Leave "appearance" empty' in prompt
    assert "Never use top_left" in prompt


def test_multi_person_pipeline_builds_hybrid_prompt_and_resolves_each_character():
    class _Context:
        async def get_current_chat_provider_id(self, umo):
            return "provider"

        async def llm_generate(self, **kwargs):
            return _Response(_plan_json())

    class _Resolver:
        def __init__(self):
            self.calls = []

        def required_core_tags_for_prompt(self, prompt):
            return ()

        async def resolve_detailed(
            self,
            *,
            llm_content,
            user_prompt,
            fixed_character,
            candidate_hints=(),
        ):
            self.calls.append((llm_content, user_prompt, fixed_character))
            return DanbooruResolveOutcome(
                text=f"verified_{llm_content}",
                status="resolved",
                canonical_tag=f"verified_{llm_content}",
                identity_tags=(f"verified_{llm_content}",),
            )

    resolver = _Resolver()
    config = {"chiyo_preset": "", "prompt_optimize_enabled": True}
    pipeline = PromptPipeline(
        context=_Context(),
        config=config,
        logger=_Logger(),
        danbooru_resolver=resolver,
        researcher=_Researcher(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=lambda text, limit: text[:limit],
    )

    result = asyncio.run(
        pipeline.build(
            _Event(),
            "若叶睦和千早爱音牵手走在放学路上",
            multi_person=True,
        )
    )

    assert result.summary["multi_person_mode"] is True
    assert result.summary["multi_person_plan_failed"] is False
    assert result.summary["planned_character_count"] == 2
    assert result.summary["resolved_character_count"] == 2
    assert result.summary["fixed_character_count"] == 0
    assert result.summary["danbooru_resolved_count"] == 2
    assert result.summary["character_slots"] == ["left", "right"]
    assert result.summary["interaction_count"] == 1
    assert result.summary["hybrid_prompt"] is True
    assert "2girls" in result.final_prompt
    assert "green-eyed girl:" in result.final_prompt
    assert "(green eyes:1.3)" in result.final_prompt
    assert "On the left" not in result.final_prompt
    assert "On the right" not in result.final_prompt
    assert "the pink-haired girl is holding the green-eyed girl's hand." in (
        result.final_prompt
    )
    assert "A second competing action" not in result.final_prompt
    assert "2girls, duo, holding hands" in result.final_prompt
    assert "Character A" not in result.final_prompt
    assert "third person" not in result.final_prompt
    assert len(resolver.calls) == 2


def test_multi_person_pipeline_protects_fixed_character_appearance():
    class _Context:
        async def get_current_chat_provider_id(self, umo):
            return "provider"

        async def llm_generate(self, **kwargs):
            return _Response(_plan_json(conflicting_fixed_appearance=True))

    class _Resolver:
        def required_core_tags_for_prompt(self, prompt):
            return ()

        async def resolve_detailed(
            self,
            *,
            llm_content,
            user_prompt,
            fixed_character,
            candidate_hints=(),
        ):
            return DanbooruResolveOutcome(
                text=llm_content,
                status="resolved",
                canonical_tag=llm_content,
                identity_tags=(llm_content,),
            )

    config = {
        "chiyo_preset": "",
        "prompt_optimize_enabled": True,
        "fixed_characters": {"若叶睦": "1girl, white hair, red eyes, fox ears, solo"},
    }
    pipeline = PromptPipeline(
        context=_Context(),
        config=config,
        logger=_Logger(),
        danbooru_resolver=_Resolver(),
        researcher=_Researcher(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=lambda text, limit: text[:limit],
    )

    result = asyncio.run(
        pipeline.build(
            _Event(),
            "若叶睦和千早爱音牵手走在放学路上",
            multi_person=True,
        )
    )

    assert result.summary["fixed_character_count"] == 1
    assert result.summary["danbooru_resolved_count"] == 1
    assert "white hair, red eyes, fox ears" in result.final_prompt
    assert "orange hair" not in result.final_prompt
    assert "solo" not in result.final_prompt


def test_close_contact_uses_one_group_and_aliases_without_forbidden_concepts():
    plan = json.dumps(
        {
            "count_tags": ["1girl", "1boy"],
            "common_tags": ["medium shot", "indoors", "split screen"],
            "characters": [
                {
                    "slot": "left",
                    "role": "pouncing fox girl",
                    "visual_label": "white-haired fox girl",
                    "identity_anchors": ["fox ears", "white hair"],
                    "name": "狐莉",
                    "danbooru_candidate": "huli",
                    "appearance": "",
                    "clothing": "white blouse",
                    "expression": "playful grin",
                    "pose": "leaning forward",
                    "props": [],
                },
                {
                    "slot": "right",
                    "role": "girl underneath",
                    "visual_label": "silver-haired vampire girl",
                    "identity_anchors": ["silver hair", "red eyes"],
                    "name": "团子",
                    "danbooru_candidate": "tuanzi",
                    "appearance": "",
                    "clothing": "black gothic dress",
                    "expression": "surprised blush",
                    "pose": "lying on her back",
                    "props": [],
                },
            ],
            "interactions": ["狐莉 is pouncing on top of 团子."],
            "relationship_tag": "pouncing",
            "composition": (
                "Both characters are clearly separated by vertical positions."
            ),
        },
        ensure_ascii=False,
    )

    class _Context:
        async def get_current_chat_provider_id(self, umo):
            return "provider"

        async def llm_generate(self, **kwargs):
            return _Response(plan)

    class _Resolver:
        def required_core_tags_for_prompt(self, prompt):
            return ()

        async def resolve_detailed(
            self,
            *,
            llm_content,
            user_prompt,
            fixed_character,
            candidate_hints=(),
        ):
            return DanbooruResolveOutcome(
                text=llm_content,
                status="resolved",
                canonical_tag=llm_content,
                identity_tags=(llm_content,),
            )

    config = {
        "chiyo_preset": "",
        "prompt_optimize_enabled": True,
        "default_artist_tags": "@artist one, @artist two",
        "fixed_characters": {
            "狐莉": "1girl, fox girl, white hair, fox ears, solo",
            "团子": "1girl, vampire, silver hair, red eyes, solo",
        },
    }
    pipeline = PromptPipeline(
        context=_Context(),
        config=config,
        logger=_Logger(),
        danbooru_resolver=_Resolver(),
        researcher=_Researcher(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=lambda text, limit: text[:limit],
    )

    result = asyncio.run(
        pipeline.build(
            _Event(),
            "狐莉扑倒团子",
            multi_person=True,
        )
    )

    assert result.summary["grouped_contact"] is True
    assert result.summary["interaction_aliases_normalized"] is True
    assert result.summary["composition_source"] == "deterministic"
    assert "white-haired fox girl: fox ears, white hair" in result.final_prompt
    assert "silver-haired vampire girl: silver hair, red eyes" in result.final_prompt
    assert "the white-haired fox girl is pouncing on top of the silver-haired vampire girl." in (
        result.final_prompt
    )
    assert "On the left" not in result.final_prompt
    assert "On the right" not in result.final_prompt
    assert "狐莉 is" not in result.final_prompt
    assert "团子 is" not in result.final_prompt
    assert "split screen" not in result.final_prompt.lower()
    assert "panel" not in result.final_prompt.lower()
    assert "clearly separated by vertical positions" not in result.final_prompt
    assert "2girls" in result.final_prompt
    assert "1boy" not in result.final_prompt
    assert "Strict identity separation" not in result.final_prompt
    assert "@artist one, @artist two" in result.final_prompt
    assert len(result.final_prompt) < 1200
    assert result.summary["character_resolution_statuses"][0]["alias"] == (
        "Character A"
    )
    assert (
        "fox ears"
        in result.summary["character_resolution_statuses"][0]["identity_tags"]
    )


def test_invalid_interaction_alias_retries_then_stops_without_ordinary_fallback():
    data = json.loads(_plan_json())
    data["interactions"] = ["Character A embraces Character C."]
    invalid_plan = json.dumps(data)

    class _Context:
        def __init__(self):
            self.calls = 0

        async def get_current_chat_provider_id(self, umo):
            return "provider"

        async def llm_generate(self, **kwargs):
            self.calls += 1
            return _Response(invalid_plan)

    class _Resolver:
        def required_core_tags_for_prompt(self, prompt):
            return ()

        async def resolve_detailed(self, **kwargs):
            raise AssertionError(
                "character resolution must not run for an invalid plan"
            )

    context = _Context()
    config = {"chiyo_preset": "", "prompt_optimize_enabled": True}
    pipeline = PromptPipeline(
        context=context,
        config=config,
        logger=_Logger(),
        danbooru_resolver=_Resolver(),
        researcher=_Researcher(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=lambda text, limit: text[:limit],
    )

    result = asyncio.run(
        pipeline.build(_Event(), "two characters embracing", multi_person=True)
    )

    assert context.calls == 2
    assert result.final_prompt == ""
    assert result.summary["multi_person_plan_failed"] is True
    assert result.summary["multi_person_error"] == "invalid_interaction_aliases"


def test_turbo_constraints_do_not_modify_multi_person_narrative_blocks():
    class _Context:
        def __init__(self):
            self.calls = 0

        async def get_current_chat_provider_id(self, umo):
            return "provider"

        async def llm_generate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return _Response(_plan_json())
            return _Response(
                json.dumps(
                    {
                        "has_constraints": True,
                        "style_tags": [],
                        "priority_tags": ["wide shot"],
                        "remove_tags": ["autumn street"],
                        "max_content_tags": 20,
                        "reason": "Protect the shared framing.",
                    }
                )
            )

    class _Resolver:
        def required_core_tags_for_prompt(self, prompt):
            return ()

        async def resolve_detailed(
            self,
            *,
            llm_content,
            user_prompt,
            fixed_character,
            candidate_hints=(),
        ):
            return DanbooruResolveOutcome(
                text=llm_content,
                status="resolved",
                canonical_tag=llm_content,
                identity_tags=(llm_content,),
            )

    config = {
        "chiyo_preset": "",
        "prompt_optimize_enabled": True,
        "low_cfg_harness_enabled": True,
    }
    pipeline = PromptPipeline(
        context=_Context(),
        config=config,
        logger=_Logger(),
        danbooru_resolver=_Resolver(),
        researcher=_Researcher(),
        get_bool=lambda key, default: bool(config.get(key, default)),
        get_int=lambda key, default: int(config.get(key, default)),
        get_float=lambda key, default: float(config.get(key, default)),
        get_str=lambda key, default: str(config.get(key, default)),
        shorten=lambda text, limit: text[:limit],
    )

    result = asyncio.run(
        pipeline.build(
            _Event(),
            "若叶睦和千早爱音牵手走在放学路上",
            multi_person=True,
        )
    )

    assert result.summary["low_cfg_harness"] is True
    assert result.summary["constraint_mode"] is True
    assert "autumn street" not in result.final_prompt
    assert "the pink-haired girl is holding the green-eyed girl's hand." in (
        result.final_prompt
    )
