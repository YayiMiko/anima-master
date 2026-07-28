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


def test_creative_expansion_rule_enriches_character_but_keeps_background_simple() -> (
    None
):
    prompt = build_llm_prompt("独自旅行的魔法少女", creative_expansion=True)

    assert "本次启用“自由发挥”模式" in prompt
    assert "通常输出 50-65 个" in prompt
    assert "背景仍只使用约 2-6 个" in prompt


def test_standard_prompt_gates_scene_tags_until_user_mentions_one_category() -> None:
    prompt = build_llm_prompt("穿白裙的少女")

    assert "场景类 Tag 门控" in prompt
    assert "如果五类均未提及" in prompt
    assert "只要用户明确提到上述任意一类" in prompt
    assert "此时不设最低 Tag 数量" in prompt


def test_creative_expansion_does_not_apply_standard_scene_gate() -> None:
    prompt = build_llm_prompt("穿白裙的少女", creative_expansion=True)

    assert "本次启用“自由发挥”模式" in prompt
    assert "场景类 Tag 门控" not in prompt


def test_raw_user_character_name_is_extracted_before_action() -> None:
    assert tags_module._user_character_queries("画若叶睦穿白色礼服") == ["若叶睦"]
    assert tags_module._user_character_queries("若叶睦") == ["若叶睦"]


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
