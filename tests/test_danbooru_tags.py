from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import danbooru_tags as tags_module  # noqa: E402
import danbooru_resolver as resolver_module  # noqa: E402
from danbooru_resolver import DanbooruResolver  # noqa: E402
from danbooru_tags import TagRecord, resolve_core_tags  # noqa: E402
from prompt_templates import build_llm_prompt  # noqa: E402


def test_safebooru_dapi_parses_character_category(monkeypatch) -> None:
    class Response:
        status_code = 200
        text = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<tags type="array">'
            '<tag type="4" count="321" name="example_character" '
            'ambiguous="false" id="1"/>'
            "</tags>"
        )

    monkeypatch.setattr(
        tags_module.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    records = tags_module._fetch_safebooru_dapi_tag(
        "example_character",
        timeout=2,
        user_agent="test",
    )

    assert records == [
        TagRecord(
            name="example_character",
            category=4,
            post_count=321,
            source="https://safebooru.org/dapi",
        )
    ]


def test_core_resolver_uses_generic_dapi_fallback(monkeypatch) -> None:
    monkeypatch.setattr(tags_module, "_fetch_donmai_tag", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        tags_module,
        "_fetch_safebooru_dapi_tag",
        lambda query, **kwargs: (
            [
                TagRecord(
                    name=query,
                    category=4,
                    post_count=321,
                    source="https://safebooru.org/dapi",
                )
            ]
            if query == "example_character"
            else []
        ),
    )

    result = resolve_core_tags(
        "example_character, 1girl, solo, military uniform",
        max_candidates=2,
    )

    assert result.text.startswith("example_character, 1girl")
    assert result.verified == (
        ("example_character", 321, "https://safebooru.org/dapi"),
    )


def test_non_fixed_character_prompt_requires_queryable_character_candidate() -> None:
    prompt = build_llm_prompt("画一个被点名的现有作品角色")

    assert "第一项必须是你认为最可信的标准 Danbooru 角色 tag" in prompt
    assert "程序会联网查询 character 分类并校正候选" in prompt


def test_default_prompt_prioritizes_visual_quality_without_fixed_tag_target() -> None:
    prompt = build_llm_prompt("独自旅行的魔法少女")

    assert "以最终图像协调、精致、有表现力和好看为优先" in prompt
    assert "不需要机械追求固定 Tag 数量" in prompt
    assert "50-65" not in prompt


def test_default_prompt_has_no_standard_scene_gate() -> None:
    prompt = build_llm_prompt("穿白裙的少女")

    assert "场景类 Tag 门控" not in prompt


def test_raw_user_character_name_is_extracted_before_action() -> None:
    assert tags_module._user_character_queries("画若叶睦穿白色礼服") == ["若叶睦"]
    assert tags_module._user_character_queries("若叶睦") == ["若叶睦"]
    assert tags_module._user_character_queries("鸣潮角色尤诺") == ["尤诺"]
    assert tags_module._user_character_queries("女孩在晨光中伸手") == []
    assert tags_module._user_character_queries("画一个女孩在海边") == []


def test_generic_candidate_can_use_scoped_dapi_evidence(monkeypatch) -> None:
    def fetch_records(query, **_kwargs):
        if query == "wrong_name_(example_work)":
            return [
                TagRecord(
                    name=query,
                    category=4,
                    post_count=900,
                    source="https://safebooru.donmai.us",
                )
            ]
        if query == "correct_name_(example_work)":
            return [
                TagRecord(
                    name=query,
                    category=0,
                    post_count=155,
                    source="https://safebooru.org/dapi",
                )
            ]
        return []

    monkeypatch.setattr(tags_module, "_fetch_tag_records", fetch_records)
    monkeypatch.setattr(
        tags_module,
        "_fetch_stable_identity_tags",
        lambda *_args, **_kwargs: ("blue hair", "blue eyes", "long hair"),
    )

    result = resolve_core_tags(
        "wrong_name_(example_work), 1girl, black hair, red eyes",
        user_prompt="示例游戏角色伊诺",
        allow_insert=True,
        candidate_hints=("correct_name_(example_work)",),
    )

    assert result.status == "resolved"
    assert result.canonical_tag == "correct_name_(example_work)"
    assert result.identity_tags == (
        "correct_name_(example_work)",
        "blue hair",
        "blue eyes",
        "long hair",
    )
    assert result.text.startswith("correct_name_(example_work), 1girl")
    assert result.evidence


def test_stable_identity_tags_are_inferred_from_repeated_solo_posts(
    monkeypatch,
) -> None:
    class Response:
        status_code = 200
        text = (
            '<posts count="5" offset="0">'
            '<post tags="example_(work) solo blue_hair blue_eyes long_hair smile"/>'
            '<post tags="example_(work) solo blue_hair blue_eyes long_hair dress"/>'
            '<post tags="example_(work) solo blue_hair blue_eyes long_hair outdoors"/>'
            '<post tags="example_(work) solo blue_hair long_hair indoors"/>'
            '<post tags="example_(work) solo red_hair red_eyes short_hair"/>'
            "</posts>"
        )

    monkeypatch.setattr(
        tags_module.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = tags_module._fetch_stable_identity_tags(
        "example_(work)",
        timeout=1,
        user_agent="test",
        cache={},
    )

    assert result == ("blue hair", "long hair", "blue eyes")


def test_common_scoped_free_tags_do_not_request_character_resolution() -> None:
    assert (
        tags_module.character_resolution_requested(
            "looking_at_viewer, depth_of_field, white dress",
            user_prompt="女孩在晨光中伸手",
        )
        is False
    )


def test_empty_lookup_cache_expires_quickly(monkeypatch) -> None:
    clock = [100.0]
    calls: list[str] = []
    monkeypatch.setattr(tags_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        tags_module,
        "_fetch_donmai_tag",
        lambda _base, query, **_kwargs: calls.append(query) or [],
    )
    monkeypatch.setattr(
        tags_module,
        "_fetch_safebooru_dapi_tag",
        lambda _query, **_kwargs: [],
    )
    cache = {}

    tags_module._fetch_tag_records(
        "missing_character",
        donmai_base_urls=("https://example.test",),
        timeout=1,
        user_agent="test",
        cache=cache,
    )
    clock[0] += 30
    tags_module._fetch_tag_records(
        "missing_character",
        donmai_base_urls=("https://example.test",),
        timeout=1,
        user_agent="test",
        cache=cache,
    )
    clock[0] += 31
    tags_module._fetch_tag_records(
        "missing_character",
        donmai_base_urls=("https://example.test",),
        timeout=1,
        user_agent="test",
        cache=cache,
    )

    assert calls == ["missing_character", "missing_character"]


def test_raw_user_name_can_correct_a_valid_but_wrong_llm_character(
    monkeypatch,
) -> None:
    def best_character(queries, **_kwargs):
        if queries == ["若叶睦"]:
            return TagRecord(
                name="wakaba_mutsumi",
                category=4,
                post_count=100,
                source="autocomplete",
            )
        return TagRecord(
            name="wrong_character",
            category=4,
            post_count=1000,
            source="tags",
        )

    monkeypatch.setattr(tags_module, "_best_character", best_character)

    result = resolve_core_tags(
        "wrong_character, 1girl, white dress",
        user_prompt="画若叶睦穿白色礼服",
        allow_insert=True,
    )

    assert result.text.startswith("wakaba_mutsumi, 1girl")


def test_danbooru_resolver_enforces_total_lookup_budget(monkeypatch) -> None:
    def slow_resolve(text, **_kwargs):
        time.sleep(1.5)
        return tags_module.CoreTagResolution(text, (), ())

    class _Logger:
        def __init__(self) -> None:
            self.warnings: list[str] = []

        def warning(self, message, *args) -> None:
            self.warnings.append(message % args)

        def info(self, *_args) -> None:
            pass

    monkeypatch.setattr(resolver_module, "resolve_core_tags", slow_resolve)
    logger = _Logger()
    resolver = DanbooruResolver(
        logger=logger,
        cache={},
        get_bool=lambda _key, default: default,
        get_int=lambda _key, default: default,
        get_float=lambda _key, _default: 1.0,
        get_str=lambda _key, default: default,
    )

    async def scenario():
        started = time.monotonic()
        result = await resolver.resolve(
            llm_content="candidate_character, 1girl",
            user_prompt="候选角色",
            fixed_character=False,
        )
        elapsed = time.monotonic() - started
        await asyncio.sleep(0.6)
        return result, elapsed

    result, elapsed = asyncio.run(scenario())

    assert result == "candidate_character, 1girl"
    assert elapsed < 1.3
    assert any("total" in warning for warning in logger.warnings)
