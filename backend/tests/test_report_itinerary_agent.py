from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from app.agents.report_itinerary_agent import agent
from app.agents.report_itinerary_agent.state import (
    ChunkExtraction,
    ChunkExtractionBatch,
    ExtractedDay,
    ExtractedReport,
)
from app.models.schemas import (
    BudgetBreakdown,
    DayPlan,
    HotelItem,
    Itinerary,
    ItineraryConversionMeta,
    MealItem,
    SpotItem,
)
from app.services.itinerary_display_service import attach_itinerary_display


BACKEND_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = BACKEND_DIR / "destination_intelligence_streamlit_reports"
ORIGINAL_EXTRACT_REPORT_WITH_LLM = agent._extract_report_with_llm


@pytest.fixture(autouse=True)
def restore_agent_extractor(monkeypatch):
    """Keep report endpoint compatibility hooks from leaking fake extractors across tests."""
    monkeypatch.setattr(agent, "_extract_report_with_llm", ORIGINAL_EXTRACT_REPORT_WITH_LLM)


class _SequenceRunnable:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, _messages):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


class _StructuredFakeLLM:
    def __init__(self, responses):
        self.runnable = _SequenceRunnable(responses)

    def with_structured_output(self, _schema, **_kwargs):
        return self.runnable


class _SchemaFakeLLM:
    model_name = "test-model"

    def __init__(self, responses):
        self.responses = responses

    def with_structured_output(self, schema, **_kwargs):
        return _SequenceRunnable([self.responses[schema]])


class _SchemaSequenceFakeLLM:
    model_name = "test-model"

    def __init__(self, responses_by_schema):
        self.responses_by_schema = responses_by_schema

    def with_structured_output(self, schema, **_kwargs):
        return _SequenceRunnable(self.responses_by_schema[schema])


@pytest.mark.parametrize(
    "heading",
    [
        "## D1｜抵达",
        "## Day 1｜抵达",
        "## 第1天｜抵达",
        "### 2026-06-25（周四）｜抵达",
    ],
)
def test_markdown_ast_chunking_preserves_day_heading_without_semantic_matching(heading) -> None:
    markdown = f"# 测试攻略\n\n## 每日安排\n\n{heading}\n\n- 前往真实地点"

    sections = agent._build_llm_extraction_sections(markdown)

    title = heading.lstrip("# ").strip()
    assert any(title in section.heading_path for section in sections)
    assert any("前往真实地点" in section.markdown for section in sections)


def test_luoyang_and_beijing_reports_keep_every_daily_heading() -> None:
    luoyang_path = next(REPORT_DIR.glob("*洛阳*.md"))
    beijing_path = next(REPORT_DIR.glob("*北京*.md"))

    luoyang_sections = agent._build_llm_extraction_sections(
        luoyang_path.read_text(encoding="utf-8")
    )
    beijing_sections = agent._build_llm_extraction_sections(
        beijing_path.read_text(encoding="utf-8")
    )

    luoyang_days = [section for section in luoyang_sections if section.heading_path[-1].startswith("2026-06-")]
    beijing_days = [section for section in beijing_sections if "D" in section.heading_path[-1] and section.heading_path[-1].startswith("2026-")]
    assert len(luoyang_days) == 6
    assert len(beijing_days) == 7
    assert any("睡到自然醒 + 补漏 + 返程" in section.title for section in luoyang_days)
    assert any("D7" in section.title for section in beijing_days)


def test_chunk_batch_retries_once_then_rejects_missing_chunk() -> None:
    sections = [
        agent._ReportExtractionSection("chunk-1", "chunk", "一", "## 一", ("一",), 1),
        agent._ReportExtractionSection("chunk-2", "chunk", "二", "## 二", ("二",), 2),
    ]
    incomplete = ChunkExtractionBatch(
        extractions=[ChunkExtraction(chunk_id="chunk-1")]
    )
    llm = _StructuredFakeLLM([incomplete, incomplete])

    with pytest.raises(agent.ReportConversionIncompleteError) as exc_info:
        agent._extract_batch_with_llm(
            llm=llm,
            sections=sections,
            destination="洛阳",
            title="洛阳攻略",
        )

    assert llm.runnable.calls == 2
    assert exc_info.value.details["missing_chunk_ids"] == ["chunk-2"]


def test_chunk_batch_accepts_complete_retry() -> None:
    sections = [
        agent._ReportExtractionSection("chunk-1", "chunk", "一", "## 一", ("一",), 1),
        agent._ReportExtractionSection("chunk-2", "chunk", "二", "## 二", ("二",), 2),
    ]
    incomplete = ChunkExtractionBatch(
        extractions=[ChunkExtraction(chunk_id="chunk-1")]
    )
    complete = ChunkExtractionBatch(
        extractions=[
            ChunkExtraction(chunk_id="chunk-1"),
            ChunkExtraction(chunk_id="chunk-2"),
        ]
    )
    llm = _StructuredFakeLLM([incomplete, complete])

    result = agent._extract_batch_with_llm(
        llm=llm,
        sections=sections,
        destination="洛阳",
        title="洛阳攻略",
    )

    assert [item.chunk_id for item in result] == ["chunk-1", "chunk-2"]
    assert llm.runnable.calls == 2


def _complete_report(start: date, count: int) -> ExtractedReport:
    return ExtractedReport(
        overview="完整概览",
        start_date=start.isoformat(),
        end_date=(start + timedelta(days=count - 1)).isoformat(),
        total_days=count,
        days=[
            ExtractedDay(
                day_index=index + 1,
                date=(start + timedelta(days=index)).isoformat(),
                theme=f"第{index + 1}天",
                full_day_text=f"第{index + 1}天完整安排",
                source_chunk_ids=[f"chunk-{index + 1}"],
            )
            for index in range(count)
        ],
    )


def _chunk_for_section(section, extracted: ExtractedReport | None = None) -> ChunkExtraction:
    return ChunkExtraction(
        chunk_id=section.section_id,
        extracted=extracted or ExtractedReport(),
    )


def test_quality_gate_rejects_partial_and_duplicate_dates() -> None:
    partial = _complete_report(date(2026, 6, 25), 5)
    with pytest.raises(agent.ReportConversionIncompleteError):
        agent._validate_extracted_report(
            partial,
            start_date=date(2026, 6, 25),
            end_date=date(2026, 6, 30),
        )

    duplicate = _complete_report(date(2026, 6, 25), 2)
    duplicate.days[1].date = duplicate.days[0].date
    with pytest.raises(agent.ReportConversionIncompleteError):
        agent._validate_extracted_report(
            duplicate,
            start_date=None,
            end_date=None,
        )


def test_v1_cache_and_changed_source_fingerprint_are_invalidated(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent.report_catalog_service, "REPORT_DIR", tmp_path)
    path = Path(agent._extracted_report_json_path("report_itinerary", "report_1"))
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": "report-section-extraction-json-v1",
                "cache_prefix": "report_itinerary",
                "source_id": "report_1",
                "extracted_report": _complete_report(date(2026, 6, 25), 1).model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    assert agent._load_extracted_report_json(
        "report_itinerary", "report_1", source_sha256="old"
    ) is None

    extracted = _complete_report(date(2026, 6, 25), 1)
    agent._save_extracted_report_json(
        cache_prefix="report_itinerary",
        source_id="report_1",
        source_sha256="current",
        extracted=extracted,
        section_count=1,
        completed_section_count=1,
        model="test",
    )
    assert agent._load_extracted_report_json(
        "report_itinerary", "report_1", source_sha256="current"
    ) is not None
    assert agent._load_extracted_report_json(
        "report_itinerary", "report_1", source_sha256="changed"
    ) is None


def test_cache_write_failure_does_not_discard_valid_conversion(tmp_path, monkeypatch) -> None:
    markdown = "# 洛阳一日攻略\n\n## 每日行程\n\n### 2026-06-25｜应天门\n\n完整安排"
    sections = agent._build_llm_extraction_sections(markdown)
    chunk_batch = ChunkExtractionBatch(
        extractions=[
            _chunk_for_section(
                section,
                _complete_report(date(2026, 6, 25), 1) if index == len(sections) - 1 else None,
            )
            for index, section in enumerate(sections)
        ]
    )
    llm = _SchemaFakeLLM(
        {
            ChunkExtractionBatch: chunk_batch,
        }
    )
    monkeypatch.setattr(agent, "build_chat_llm", lambda *_args, **_kwargs: llm)
    monkeypatch.setattr(
        agent,
        "_save_extracted_report_json",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(agent.report_catalog_service, "REPORT_DIR", tmp_path)

    result = agent._extract_report_with_llm(
        markdown=markdown,
        destination="洛阳",
        title="洛阳一日攻略",
        source_id="report_1",
        cache_prefix="report_itinerary",
        start_date=date(2026, 6, 25),
        end_date=date(2026, 6, 25),
    )

    assert result.total_days == 1
    assert result.days[0].theme == "第1天"


def test_chunk_checkpoint_saves_successful_batches_and_resumes_missing_chunks(
    tmp_path, monkeypatch
) -> None:
    markdown = "# 洛阳两日攻略\n\n## 每日行程\n\n### 2026-06-25｜应天门\n\n完整安排\n\n### 2026-06-26｜龙门石窟\n\n完整安排"
    sections = agent._build_llm_extraction_sections(markdown)
    first_chunk = _chunk_for_section(sections[0])
    checkpoint_chunks = {first_chunk.chunk_id: first_chunk}
    source_sha256 = agent._source_sha256(markdown)
    monkeypatch.setattr(agent.report_catalog_service, "REPORT_DIR", tmp_path)
    agent._save_chunk_checkpoint(
        cache_prefix="report_itinerary",
        source_id="report_1",
        source_sha256=source_sha256,
        model="test-model",
        chunk_count=len(sections),
        chunks=checkpoint_chunks,
    )
    remaining_chunks = [
        _chunk_for_section(
            section,
            _complete_report(date(2026, 6, 25), 2) if index == len(sections) - 1 else None,
        )
        for index, section in enumerate(sections)
        if section.section_id != first_chunk.chunk_id
    ]
    llm = _SchemaFakeLLM(
        {
            ChunkExtractionBatch: ChunkExtractionBatch(extractions=remaining_chunks),
        }
    )
    monkeypatch.setattr(agent, "build_chat_llm", lambda *_args, **_kwargs: llm)

    result = agent._extract_report_with_llm(
        markdown=markdown,
        destination="洛阳",
        title="洛阳两日攻略",
        source_id="report_1",
        cache_prefix="report_itinerary",
        start_date=date(2026, 6, 25),
        end_date=date(2026, 6, 26),
    )

    assert result.total_days == 2
    assert not agent._chunk_checkpoint_path("report_itinerary", "report_1").exists()
    assert agent._load_extracted_report_json(
        "report_itinerary", "report_1", source_sha256=source_sha256
    ) is not None


def test_chunk_checkpoint_ignores_mismatched_source_fingerprint(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent.report_catalog_service, "REPORT_DIR", tmp_path)
    chunk = ChunkExtraction(chunk_id="chunk-1")
    agent._save_chunk_checkpoint(
        cache_prefix="report_itinerary",
        source_id="report_1",
        source_sha256="old",
        model="test-model",
        chunk_count=1,
        chunks={chunk.chunk_id: chunk},
    )

    assert agent._load_chunk_checkpoint(
        cache_prefix="report_itinerary",
        source_id="report_1",
        source_sha256="new",
        model="test-model",
        chunk_count=1,
    ) == {}


def test_force_rebuild_deletes_cache_and_checkpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent.report_catalog_service, "REPORT_DIR", tmp_path)
    markdown = "# 洛阳一日攻略\n\n## 每日行程\n\n### 2026-06-25｜应天门\n\n完整安排"
    source_sha256 = agent._source_sha256(markdown)
    old_report = _complete_report(date(2026, 6, 25), 1)
    agent._save_extracted_report_json(
        cache_prefix="report_itinerary",
        source_id="report_1",
        source_sha256=source_sha256,
        extracted=old_report,
        section_count=1,
        completed_section_count=1,
        model="test-model",
    )
    agent._save_chunk_checkpoint(
        cache_prefix="report_itinerary",
        source_id="report_1",
        source_sha256=source_sha256,
        model="test-model",
        chunk_count=1,
        chunks={"stale": ChunkExtraction(chunk_id="stale")},
    )
    sections = agent._build_llm_extraction_sections(markdown)
    llm = _SchemaFakeLLM(
        {
            ChunkExtractionBatch: ChunkExtractionBatch(
                extractions=[
                    _chunk_for_section(
                        section,
                        old_report if index == len(sections) - 1 else None,
                    )
                    for index, section in enumerate(sections)
                ]
            ),
        }
    )
    monkeypatch.setattr(agent, "build_chat_llm", lambda *_args, **_kwargs: llm)

    agent._extract_report_with_llm(
        markdown=markdown,
        destination="洛阳",
        title="洛阳一日攻略",
        source_id="report_1",
        cache_prefix="report_itinerary",
        force_rebuild=True,
        start_date=date(2026, 6, 25),
        end_date=date(2026, 6, 25),
    )

    payload = json.loads(
        Path(agent._extracted_report_json_path("report_itinerary", "report_1")).read_text(
            encoding="utf-8"
        )
    )
    assert payload["completed_chunk_count"] == len(sections)
    assert not agent._chunk_checkpoint_path("report_itinerary", "report_1").exists()


def test_provider_failure_keeps_chunk_checkpoint_without_formal_cache(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(agent.report_catalog_service, "REPORT_DIR", tmp_path)
    markdown = "# 洛阳两日攻略\n\n## 每日行程\n\n### 2026-06-25｜应天门\n\n完整安排\n\n### 2026-06-26｜龙门石窟\n\n完整安排"
    sections = agent._build_llm_extraction_sections(markdown)
    monkeypatch.setattr(agent, "_MAX_BATCH_CHUNKS", 1)
    monkeypatch.setattr(agent, "_MAX_BATCH_CHARS", 10_000)
    monkeypatch.setattr(agent.config, "REPORT_ITINERARY_MAX_CONCURRENT_BATCHES", 1)
    monkeypatch.setattr(agent, "build_chat_llm", lambda *_args, **_kwargs: _SchemaFakeLLM({}))

    calls = {"count": 0}

    def fake_extract_batch(*, sections, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return [_chunk_for_section(sections[0], _complete_report(date(2026, 6, 25), 1))]
        raise agent.ReportConversionUnavailableError()

    monkeypatch.setattr(agent, "_extract_batch_with_llm", fake_extract_batch)

    with pytest.raises(agent.ReportConversionUnavailableError):
        agent._extract_report_with_llm(
            markdown=markdown,
            destination="洛阳",
            title="洛阳一日攻略",
            source_id="report_1",
            cache_prefix="report_itinerary",
            start_date=date(2026, 6, 25),
            end_date=date(2026, 6, 26),
        )

    assert agent._chunk_checkpoint_path("report_itinerary", "report_1").exists()
    assert not Path(agent._extracted_report_json_path("report_itinerary", "report_1")).exists()


def test_display_uses_typed_overview_hides_unknown_costs_and_deduplicates_pois() -> None:
    meta = ItineraryConversionMeta(
        kind="report_itinerary",
        version="report-itinerary-llm-v2",
        source_id="report_1",
        source_sha256="abc",
        chunk_count=2,
        completed_chunk_count=2,
        quality_passed=True,
    )
    repeated_hotel = HotelItem(
        name="同一家酒店",
        poi_id="hotel-poi",
        latitude=34.1,
        longitude=112.1,
    )
    itinerary = Itinerary(
        trip_id="report_itinerary_test",
        destination="洛阳",
        summary="不应依赖标签匹配",
        days=[
            DayPlan(
                day_index=1,
                date=date(2026, 6, 25),
                theme="第一天",
                spots=[SpotItem(name="应天门", poi_id="spot-poi", latitude=34.2, longitude=112.2)],
                meals=[MealItem(name="少辣晚餐", meal_type="晚餐")],
                hotel=repeated_hotel,
            ),
            DayPlan(
                day_index=2,
                date=date(2026, 6, 26),
                theme="第二天",
                hotel=repeated_hotel.model_copy(deep=True),
            ),
        ],
        budget_breakdown=BudgetBreakdown(total=3200),
        estimated_budget=3200,
        overview_facts=[
            {"key": "travelers", "label": "出行人", "value": "2人"},
            {"key": "pace", "label": "旅行模式", "value": "轻松"},
        ],
        conversion_meta=meta,
    )

    attach_itinerary_display(itinerary)

    assert next(item.value for item in itinerary.display.overview if item.key == "travelers") == "2人"
    assert itinerary.display.day_budget_items == []
    assert len([point for point in itinerary.display.map_points if point.kind == "hotel"]) == 1
    assert len(itinerary.display.hotel_recommendations) == 1
