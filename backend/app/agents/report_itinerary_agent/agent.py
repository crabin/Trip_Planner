from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as DateType, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, TypeVar

from markdown_it import MarkdownIt
from pydantic import BaseModel, ValidationError

from app import config
from app.agents.report_itinerary_agent.prompts import (
    SYSTEM_PROMPT,
    build_chunk_batch_prompt,
    build_consolidation_prompt,
)
from app.agents.report_itinerary_agent.state import (
    ChunkExtraction,
    ChunkExtractionBatch,
    ExtractedDay,
    ExtractedMeal,
    ExtractedReport,
    ExtractedSpot,
    ReportDayDraft,
    ReportExtractionSection,
)
from app.agents.trip_planner_agent.llms import LLMSettings, build_chat_llm
from app.models.schemas import (
    BudgetBreakdown,
    DayPlan,
    DeepPlanDocument,
    HotelItem,
    Itinerary,
    ItineraryConversionMeta,
    ItineraryOverviewFact,
    MealItem,
    SpotItem,
    TransportItem,
)
import app.services.report_catalog_service as report_catalog_service
from app.services.itinerary_display_service import attach_itinerary_display
from app.services.trip_service import _maybe_enrich_itinerary_with_map_data


_CONVERSION_VERSION = "report-itinerary-llm-v3"
_EXTRACTED_REPORT_JSON_VERSION = "report-section-extraction-json-v3"
_MAX_BATCH_CHUNKS = 6
_MAX_BATCH_CHARS = 6000
_MAX_CONCURRENT_BATCHES = 3
_STRUCTURED_ATTEMPTS = 2


class ReportConversionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        retryable: bool = True,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            **self.details,
        }


class ReportConversionUnavailableError(ReportConversionError):
    def __init__(self, message: str = "结构化转换服务暂时不可用，请稍后重试。") -> None:
        super().__init__(
            "report_conversion_unavailable",
            message,
            status_code=503,
        )


class ReportConversionIncompleteError(ReportConversionError):
    def __init__(
        self,
        message: str = "Report 小结提取不完整，未生成结果页。",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            "report_conversion_incomplete",
            message,
            status_code=422,
            details=details,
        )


_ReportDayDraft = ReportDayDraft
_ExtractedSpot = ExtractedSpot
_ExtractedMeal = ExtractedMeal
_ExtractedDay = ExtractedDay
_ExtractedReport = ExtractedReport
_ReportExtractionSection = ReportExtractionSection

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


def _cache_trip_id(prefix: str, source_id: str) -> str:
    digest = sha256(source_id.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _source_sha256(markdown: str) -> str:
    return sha256(markdown.encode("utf-8")).hexdigest()


def _extracted_report_json_dir() -> Path:
    return report_catalog_service.REPORT_DIR / "structured_itineraries"


def _extracted_report_json_path(cache_prefix: str, source_id: str) -> str:
    return str(_extracted_report_json_dir() / f"{_cache_trip_id(cache_prefix, source_id)}.json")


def _extracted_report_json_file(cache_prefix: str, source_id: str) -> Path:
    return _extracted_report_json_dir() / f"{_cache_trip_id(cache_prefix, source_id)}.json"


def _chunk_checkpoint_path(cache_prefix: str, source_id: str) -> Path:
    return _extracted_report_json_dir() / f"{_cache_trip_id(cache_prefix, source_id)}.chunks.json"


def _load_extracted_report_json(
    cache_prefix: str,
    source_id: str,
    *,
    source_sha256: str | None = None,
) -> _ExtractedReport | None:
    path = _extracted_report_json_dir() / f"{_cache_trip_id(cache_prefix, source_id)}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != _EXTRACTED_REPORT_JSON_VERSION:
            return None
        if payload.get("source_id") != source_id or payload.get("cache_prefix") != cache_prefix:
            return None
        if source_sha256 is not None and payload.get("source_sha256") != source_sha256:
            return None
        if payload.get("quality_passed") is not True:
            return None
        if payload.get("completed_chunk_count") != payload.get("chunk_count"):
            return None
        return _ExtractedReport.model_validate(payload.get("extracted_report"))
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return None


def _checkpoint_key(
    *,
    cache_prefix: str,
    source_id: str,
    source_sha256: str,
    model: str,
    chunk_count: int,
) -> dict[str, Any]:
    return {
        "version": _EXTRACTED_REPORT_JSON_VERSION,
        "converter_version": _CONVERSION_VERSION,
        "cache_prefix": cache_prefix,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "model": model,
        "chunk_count": chunk_count,
    }


def _load_chunk_checkpoint(
    *,
    cache_prefix: str,
    source_id: str,
    source_sha256: str,
    model: str,
    chunk_count: int,
) -> dict[str, ChunkExtraction]:
    path = _chunk_checkpoint_path(cache_prefix, source_id)
    if not path.is_file():
        return {}
    expected = _checkpoint_key(
        cache_prefix=cache_prefix,
        source_id=source_id,
        source_sha256=source_sha256,
        model=model,
        chunk_count=chunk_count,
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            if payload.get(key) != value:
                return {}
        chunks = payload.get("chunks")
        if not isinstance(chunks, dict):
            return {}
        loaded: dict[str, ChunkExtraction] = {}
        for chunk_id, chunk_payload in chunks.items():
            chunk = ChunkExtraction.model_validate(chunk_payload)
            if chunk.chunk_id == chunk_id:
                loaded[chunk_id] = chunk
        return loaded
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return {}


def _save_chunk_checkpoint(
    *,
    cache_prefix: str,
    source_id: str,
    source_sha256: str,
    model: str,
    chunk_count: int,
    chunks: dict[str, ChunkExtraction],
) -> None:
    json_dir = _extracted_report_json_dir()
    json_dir.mkdir(parents=True, exist_ok=True)
    path = _chunk_checkpoint_path(cache_prefix, source_id)
    temp_path = path.with_suffix(".chunks.json.tmp")
    payload = {
        **_checkpoint_key(
            cache_prefix=cache_prefix,
            source_id=source_id,
            source_sha256=source_sha256,
            model=model,
            chunk_count=chunk_count,
        ),
        "completed_chunk_count": len(chunks),
        "chunks": {
            chunk_id: chunk.model_dump(mode="json")
            for chunk_id, chunk in sorted(chunks.items())
        },
    }
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _delete_chunk_checkpoint(cache_prefix: str, source_id: str) -> None:
    try:
        _chunk_checkpoint_path(cache_prefix, source_id).unlink(missing_ok=True)
    except OSError:
        pass


def _delete_extracted_report_json(cache_prefix: str, source_id: str) -> None:
    try:
        _extracted_report_json_file(cache_prefix, source_id).unlink(missing_ok=True)
    except OSError:
        pass


def _save_extracted_report_json(
    *,
    cache_prefix: str,
    source_id: str,
    source_sha256: str,
    extracted: _ExtractedReport,
    section_count: int,
    completed_section_count: int | None = None,
    model: str = "",
) -> None:
    json_dir = _extracted_report_json_dir()
    json_dir.mkdir(parents=True, exist_ok=True)
    path = json_dir / f"{_cache_trip_id(cache_prefix, source_id)}.json"
    temp_path = path.with_suffix(".json.tmp")
    completed = completed_section_count if completed_section_count is not None else section_count
    payload = {
        "version": _EXTRACTED_REPORT_JSON_VERSION,
        "converter_version": _CONVERSION_VERSION,
        "cache_prefix": cache_prefix,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "model": model,
        "chunk_count": section_count,
        "completed_chunk_count": completed,
        "quality_passed": True,
        "extracted_report": extracted.model_dump(mode="json"),
    }
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _parse_date(value: str | None) -> DateType | None:
    if not value:
        return None
    try:
        return DateType.fromisoformat(value)
    except ValueError:
        return None


def _build_llm_extraction_sections(
    markdown: str,
    destination: str = "",
) -> list[_ReportExtractionSection]:
    """Split Markdown by syntax only; semantic classification belongs to the LLM."""

    del destination
    lines = markdown.splitlines(keepends=True)
    tokens = MarkdownIt("commonmark").parse(markdown)
    headings: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.map is None:
            continue
        level = int(token.tag.removeprefix("h"))
        if level not in {1, 2, 3}:
            continue
        title = tokens[index + 1].content.strip() if index + 1 < len(tokens) else ""
        headings.append((level, token.map[0], title))

    if not headings:
        return [
            _ReportExtractionSection(
                section_id="chunk-001-full-report",
                section_type="chunk",
                title="完整 Report",
                markdown=markdown,
                heading_path=("完整 Report",),
                order=1,
            )
        ]

    sections: list[_ReportExtractionSection] = []
    order = 0
    first_h2_start = next((start for level, start, _ in headings if level == 2), len(lines))
    root_title = next((title for level, _, title in headings if level == 1), "Report 概览")
    root_markdown = "".join(lines[:first_h2_start]).strip()
    if root_markdown:
        order += 1
        sections.append(
            _make_section(
                order=order,
                heading_path=(root_title,),
                markdown=root_markdown,
            )
        )

    h2_headings = [(start, title) for level, start, title in headings if level == 2]
    if not h2_headings:
        if sections:
            return sections
        return [
            _make_section(order=1, heading_path=(root_title,), markdown=markdown.strip())
        ]

    h3_headings = [(start, title) for level, start, title in headings if level == 3]
    for h2_index, (h2_start, h2_title) in enumerate(h2_headings):
        h2_end = h2_headings[h2_index + 1][0] if h2_index + 1 < len(h2_headings) else len(lines)
        children = [(start, title) for start, title in h3_headings if h2_start < start < h2_end]
        preamble_end = children[0][0] if children else h2_end
        preamble = "".join(lines[h2_start:preamble_end]).strip()
        if preamble:
            order += 1
            sections.append(
                _make_section(
                    order=order,
                    heading_path=(h2_title,),
                    markdown=preamble,
                )
            )
        for child_index, (child_start, child_title) in enumerate(children):
            child_end = children[child_index + 1][0] if child_index + 1 < len(children) else h2_end
            child_markdown = "".join(lines[child_start:child_end]).strip()
            if not child_markdown:
                continue
            order += 1
            sections.append(
                _make_section(
                    order=order,
                    heading_path=(h2_title, child_title),
                    markdown=child_markdown,
                )
            )
    return sections


def _make_section(
    *,
    order: int,
    heading_path: tuple[str, ...],
    markdown: str,
) -> _ReportExtractionSection:
    path_text = " / ".join(heading_path)
    digest = sha256(path_text.encode("utf-8")).hexdigest()[:8]
    return _ReportExtractionSection(
        section_id=f"chunk-{order:03d}-{digest}",
        section_type="chunk",
        title=heading_path[-1],
        markdown=markdown,
        heading_path=heading_path,
        order=order,
    )


def _batch_sections(
    sections: list[_ReportExtractionSection],
) -> list[list[_ReportExtractionSection]]:
    batches: list[list[_ReportExtractionSection]] = []
    current: list[_ReportExtractionSection] = []
    current_chars = 0
    for section in sections:
        size = len(section.markdown)
        if current and (
            len(current) >= _MAX_BATCH_CHUNKS or current_chars + size > _MAX_BATCH_CHARS
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(section)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def _structured_runnable(llm: Any, schema: type[_SchemaT]):
    try:
        return llm.with_structured_output(
            schema,
            method="function_calling",
            strict=False,
        )
    except Exception as exc:
        raise ReportConversionUnavailableError("当前模型不支持严格结构化输出。") from exc


def _invoke_structured(
    *,
    llm: Any,
    schema: type[_SchemaT],
    user_prompt: str,
) -> _SchemaT:
    runnable = _structured_runnable(llm, schema)
    last_error: Exception | None = None
    validation_error: ValidationError | None = None
    for _ in range(_STRUCTURED_ATTEMPTS):
        try:
            result = runnable.invoke([("system", SYSTEM_PROMPT), ("human", user_prompt)])
            return result if isinstance(result, schema) else schema.model_validate(result)
        except ReportConversionError:
            raise
        except ValidationError as exc:
            validation_error = exc
            last_error = exc
        except Exception as exc:
            last_error = exc
    if validation_error is not None:
        raise ReportConversionIncompleteError(
            details={"reason": "structured_output_validation_failed"}
        ) from validation_error
    raise ReportConversionUnavailableError() from last_error


def _extract_batch_with_llm(
    *,
    llm: Any,
    sections: list[_ReportExtractionSection],
    destination: str,
    title: str,
) -> list[ChunkExtraction]:
    prompt = build_chunk_batch_prompt(
        sections=sections,
        destination=destination,
        title=title,
    )
    expected_ids = [section.section_id for section in sections]
    last_received: list[str] = []
    for _ in range(_STRUCTURED_ATTEMPTS):
        batch = _invoke_structured(
            llm=llm,
            schema=ChunkExtractionBatch,
            user_prompt=prompt,
        )
        received_ids = [item.chunk_id for item in batch.extractions]
        last_received = received_ids
        if len(received_ids) == len(set(received_ids)) and set(received_ids) == set(expected_ids):
            by_id = {item.chunk_id: item for item in batch.extractions}
            return [by_id[chunk_id] for chunk_id in expected_ids]
    missing = sorted(set(expected_ids) - set(last_received))
    unexpected = sorted(set(last_received) - set(expected_ids))
    raise ReportConversionIncompleteError(
        details={"missing_chunk_ids": missing, "unexpected_chunk_ids": unexpected}
    )


def _extract_report_section_with_llm(
    *,
    llm: Any,
    section: _ReportExtractionSection,
    destination: str,
    title: str,
) -> _ExtractedReport | None:
    extraction = _extract_batch_with_llm(
        llm=llm,
        sections=[section],
        destination=destination,
        title=title,
    )[0]
    return extraction.extracted


def _merge_unique_by_key(items: list[Any], key_func) -> list[Any]:
    seen: set[tuple[Any, ...]] = set()
    merged: list[Any] = []
    for item in items:
        key = key_func(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_day(existing: ExtractedDay, incoming: ExtractedDay) -> ExtractedDay:
    return existing.model_copy(
        update={
            "theme": existing.theme or incoming.theme,
            "full_day_text": "\n\n".join(
                text
                for text in [existing.full_day_text.strip(), incoming.full_day_text.strip()]
                if text
            ),
            "spots": _merge_unique_by_key(
                [*existing.spots, *incoming.spots],
                lambda spot: (spot.name.strip(), spot.map_query.strip()),
            ),
            "meals": _merge_unique_by_key(
                [*existing.meals, *incoming.meals],
                lambda meal: (meal.name.strip(), meal.meal_type.strip(), meal.map_query.strip()),
            ),
            "hotel_name": existing.hotel_name or incoming.hotel_name,
            "hotel_query": existing.hotel_query or incoming.hotel_query,
            "hotel_level": existing.hotel_level or incoming.hotel_level,
            "hotel_cost": existing.hotel_cost if existing.hotel_cost is not None else incoming.hotel_cost,
            "transport_note": existing.transport_note or incoming.transport_note,
            "transport": _merge_unique_by_key(
                [*existing.transport, *incoming.transport],
                lambda item: (
                    item.mode,
                    item.from_place,
                    item.to_place,
                    item.duration,
                    item.estimated_cost,
                ),
            ),
            "source_chunk_ids": list(
                dict.fromkeys([*existing.source_chunk_ids, *incoming.source_chunk_ids])
            ),
        }
    )


def _consolidate_extractions(extractions: list[ChunkExtraction]) -> _ExtractedReport:
    overview = ""
    overview_facts = []
    tips: list[str] = []
    days_by_key: dict[tuple[int, str], ExtractedDay] = {}
    total_budget = 0.0
    start_date: str | None = None
    end_date: str | None = None
    source_chunk_ids: list[str] = []

    for chunk in extractions:
        extracted = chunk.extracted
        if extracted.overview and not overview:
            overview = extracted.overview
        for fact in extracted.overview_facts:
            if not fact.source_chunk_ids:
                fact = fact.model_copy(update={"source_chunk_ids": [chunk.chunk_id]})
            overview_facts.append(fact)
        if extracted.total_budget > 0:
            total_budget = total_budget or extracted.total_budget
        start_date = start_date or extracted.start_date
        end_date = extracted.end_date or end_date
        for tip in extracted.tips:
            if tip and tip not in tips:
                tips.append(tip)
        source_chunk_ids.append(chunk.chunk_id)
        for day in extracted.days:
            day_sources = day.source_chunk_ids or [chunk.chunk_id]
            day = day.model_copy(update={"source_chunk_ids": day_sources})
            key = (day.day_index, day.date or "")
            days_by_key[key] = _merge_day(days_by_key[key], day) if key in days_by_key else day

    deduped_facts = _merge_unique_by_key(
        overview_facts,
        lambda fact: (fact.key.strip(), fact.value.strip()),
    )
    days = sorted(days_by_key.values(), key=lambda item: (item.day_index, item.date or ""))
    return _ExtractedReport(
        overview=overview,
        overview_facts=deduped_facts,
        start_date=start_date,
        end_date=end_date,
        total_days=len(days) or None,
        total_budget=total_budget,
        tips=tips,
        days=days,
        source_chunk_ids=list(dict.fromkeys(source_chunk_ids)),
    )


def _extract_report_with_llm(
    *,
    markdown: str,
    destination: str,
    title: str,
    source_id: str | None = None,
    cache_prefix: str | None = None,
    force_rebuild: bool = False,
    start_date: DateType | None = None,
    end_date: DateType | None = None,
) -> _ExtractedReport:
    fingerprint = _source_sha256(markdown)
    if source_id and cache_prefix and force_rebuild:
        _delete_extracted_report_json(cache_prefix, source_id)
        _delete_chunk_checkpoint(cache_prefix, source_id)
    if source_id and cache_prefix and not force_rebuild:
        cached = _load_extracted_report_json(
            cache_prefix,
            source_id,
            source_sha256=fingerprint,
        )
        if cached is not None:
            return _validate_extracted_report(cached, start_date=start_date, end_date=end_date)

    try:
        llm = build_chat_llm(
            LLMSettings(
                api_key=config.LLM_API_KEY,
                model=config.LLM_MODEL,
                base_url=config.LLM_BASE_URL,
                timeout_seconds=config.REPORT_ITINERARY_LLM_TIMEOUT_SECONDS,
                max_retries=config.LLM_MAX_RETRIES,
            )
        )
    except Exception as exc:
        raise ReportConversionUnavailableError() from exc
    if llm is None:
        raise ReportConversionUnavailableError()

    sections = _build_llm_extraction_sections(markdown, destination)
    batches = _batch_sections(sections)
    model = _model_name(llm)
    expected_ids = {section.section_id for section in sections}
    checkpoint_chunks: dict[str, ChunkExtraction] = {}
    if source_id and cache_prefix and not force_rebuild:
        checkpoint_chunks = _load_chunk_checkpoint(
            cache_prefix=cache_prefix,
            source_id=source_id,
            source_sha256=fingerprint,
            model=model,
            chunk_count=len(sections),
        )
        checkpoint_chunks = {
            chunk_id: chunk
            for chunk_id, chunk in checkpoint_chunks.items()
            if chunk_id in expected_ids
        }

    missing_batches = [
        (
            index,
            [
                section
                for section in batch
                if section.section_id not in checkpoint_chunks
            ],
        )
        for index, batch in enumerate(batches)
        if any(section.section_id not in checkpoint_chunks for section in batch)
    ]
    max_workers = max(
        1,
        min(
            config.REPORT_ITINERARY_MAX_CONCURRENT_BATCHES,
            _MAX_CONCURRENT_BATCHES,
            len(missing_batches) or 1,
        ),
    )
    if missing_batches:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    _extract_batch_with_llm,
                    llm=llm,
                    sections=batch,
                    destination=destination,
                    title=title,
                ): index
                for index, batch in missing_batches
            }
            for future in as_completed(future_map):
                batch_index = future_map[future]
                batch_result = future.result()
                for extraction in batch_result:
                    checkpoint_chunks[extraction.chunk_id] = extraction
                if source_id and cache_prefix:
                    try:
                        _save_chunk_checkpoint(
                            cache_prefix=cache_prefix,
                            source_id=source_id,
                            source_sha256=fingerprint,
                            model=model,
                            chunk_count=len(sections),
                            chunks=checkpoint_chunks,
                        )
                    except OSError:
                        pass

    extractions = [
        checkpoint_chunks[section.section_id]
        for section in sections
        if section.section_id in checkpoint_chunks
    ]
    completed_ids = {item.chunk_id for item in extractions}
    if completed_ids != expected_ids:
        raise ReportConversionIncompleteError(
            details={"missing_chunk_ids": sorted(expected_ids - completed_ids)}
        )

    consolidated = _consolidate_extractions(extractions)
    consolidated = _validate_extracted_report(
        consolidated,
        start_date=start_date,
        end_date=end_date,
    )
    if source_id and cache_prefix:
        try:
            _save_extracted_report_json(
                cache_prefix=cache_prefix,
                source_id=source_id,
                source_sha256=fingerprint,
                extracted=consolidated,
                section_count=len(sections),
                completed_section_count=len(extractions),
                model=model,
            )
            _delete_chunk_checkpoint(cache_prefix, source_id)
        except OSError:
            pass
    return consolidated


def _model_name(llm: Any | None = None) -> str:
    value = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    return str(value or config.LLM_MODEL or "")


def _validate_extracted_report(
    extracted: _ExtractedReport,
    *,
    start_date: DateType | None,
    end_date: DateType | None,
) -> _ExtractedReport:
    days = sorted(extracted.days, key=lambda item: item.day_index)
    if not days:
        raise ReportConversionIncompleteError(details={"reason": "no_days"})
    expected_indices = list(range(1, len(days) + 1))
    actual_indices = [day.day_index for day in days]
    if actual_indices != expected_indices:
        raise ReportConversionIncompleteError(
            details={"reason": "non_contiguous_day_indices", "day_indices": actual_indices}
        )
    for day in days:
        has_structured_content = bool(
            day.spots
            or day.meals
            or day.hotel_name.strip()
            or day.transport
            or day.transport_note.strip()
        )
        if not day.full_day_text.strip() and not has_structured_content:
            raise ReportConversionIncompleteError(details={"reason": "incomplete_day_content"})

    resolved_start = start_date or _parse_date(extracted.start_date)
    resolved_end = end_date or _parse_date(extracted.end_date)
    parsed_dates = [_parse_date(day.date) for day in days]
    if resolved_start is not None and resolved_end is not None:
        expected_count = (resolved_end - resolved_start).days + 1
        expected_dates = [resolved_start + timedelta(days=index) for index in range(expected_count)]
        if expected_count < 1 or len(days) != expected_count or parsed_dates != expected_dates:
            raise ReportConversionIncompleteError(
                details={
                    "reason": "date_range_mismatch",
                    "expected_days": expected_count,
                    "actual_days": len(days),
                }
            )
    elif any(value is not None for value in parsed_dates):
        if any(value is None for value in parsed_dates) or len(set(parsed_dates)) != len(parsed_dates):
            raise ReportConversionIncompleteError(details={"reason": "invalid_day_dates"})
        assert all(value is not None for value in parsed_dates)
        for previous, current in zip(parsed_dates, parsed_dates[1:]):
            if current != previous + timedelta(days=1):
                raise ReportConversionIncompleteError(details={"reason": "non_contiguous_day_dates"})
        resolved_start = parsed_dates[0]
        resolved_end = parsed_dates[-1]

    if extracted.total_days is not None and extracted.total_days != len(days):
        raise ReportConversionIncompleteError(
            details={"reason": "total_days_mismatch", "actual_days": len(days)}
        )
    return extracted.model_copy(
        update={
            "days": days,
            "start_date": resolved_start.isoformat() if resolved_start else extracted.start_date,
            "end_date": resolved_end.isoformat() if resolved_end else extracted.end_date,
            "total_days": len(days),
        }
    )


def _apply_report_budget(itinerary: Itinerary, report_budget: float) -> Itinerary:
    itinerary.estimated_budget = report_budget if report_budget > 0 else 0.0
    itinerary.budget_breakdown = BudgetBreakdown(total=itinerary.estimated_budget)
    return itinerary


def _itinerary_from_extracted_report(
    *,
    source_id: str,
    source_sha256: str,
    extracted: _ExtractedReport,
    destination: str,
    title: str,
    cache_prefix: str,
    chunk_count: int,
) -> Itinerary:
    days: list[DayPlan] = []
    for extracted_day in extracted.days:
        spots = [
            SpotItem(
                name=spot.name.strip(),
                start_time=spot.start_time,
                end_time=spot.end_time,
                description=spot.description.strip() or None,
                estimated_cost=spot.estimated_cost,
                location=spot.map_query.strip() or None,
                map_query=spot.map_query.strip() or None,
            )
            for spot in extracted_day.spots
            if spot.name.strip()
        ]
        meals = [
            MealItem(
                name=meal.name.strip(),
                meal_type=meal.meal_type.strip() or "餐饮",
                estimated_cost=meal.estimated_cost,
                notes=meal.notes.strip() or None,
                map_query=meal.map_query.strip() or None,
                data_source="destination_intelligence_report",
            )
            for meal in extracted_day.meals
            if meal.name.strip()
        ]
        hotel_name = extracted_day.hotel_name.strip()
        hotel = (
            HotelItem(
                name=hotel_name,
                level=extracted_day.hotel_level.strip() or None,
                estimated_cost=extracted_day.hotel_cost,
                location=extracted_day.hotel_query.strip() or None,
                map_query=extracted_day.hotel_query.strip() or None,
                data_source="destination_intelligence_report",
            )
            if hotel_name
            else None
        )
        transport = [
            TransportItem(
                mode=item.mode,
                from_place=item.from_place,
                to_place=item.to_place,
                estimated_cost=item.estimated_cost,
                duration=item.duration,
            )
            for item in extracted_day.transport
        ]
        if not transport and extracted_day.transport_note.strip():
            transport.append(
                TransportItem(
                    mode="行程交通",
                    duration=extracted_day.transport_note.strip(),
                )
            )
        days.append(
            DayPlan(
                day_index=extracted_day.day_index,
                date=_parse_date(extracted_day.date),
                theme=extracted_day.theme.strip() or f"第{extracted_day.day_index}天",
                spots=spots,
                meals=meals,
                hotel=hotel,
                transport=transport,
                notes=[
                    extracted_day.full_day_text.strip()
                    or extracted_day.theme.strip()
                    or (extracted_day.date or "")
                ],
            )
        )

    overview_facts = [
        ItineraryOverviewFact(
            key=fact.key,
            label=fact.label,
            value=fact.value,
            source_chunk_ids=fact.source_chunk_ids,
        )
        for fact in extracted.overview_facts
        if fact.key.strip() and fact.value.strip()
    ]
    itinerary = Itinerary(
        trip_id=_cache_trip_id(cache_prefix, source_id),
        destination=destination,
        summary=extracted.overview.strip() or title,
        days=days,
        estimated_budget=extracted.total_budget,
        budget_breakdown=BudgetBreakdown(total=extracted.total_budget),
        tips=extracted.tips,
        source_notes=[
            "结果页由 Destination Intelligence Report 的结构化 LLM 转换生成。",
            f"Report/Deep source id: {source_id}",
        ],
        overview_facts=overview_facts,
        conversion_meta=ItineraryConversionMeta(
            kind="report_itinerary" if cache_prefix == "report_itinerary" else "deep_itinerary",
            version=_CONVERSION_VERSION,
            source_id=source_id,
            source_sha256=source_sha256,
            model=config.LLM_MODEL,
            chunk_count=chunk_count,
            completed_chunk_count=chunk_count,
            quality_passed=True,
        ),
    )
    itinerary = _maybe_enrich_itinerary_with_map_data(itinerary, city=destination)
    return attach_itinerary_display(_apply_report_budget(itinerary, extracted.total_budget))


def _needs_rebuild_from_cache(
    itinerary: Itinerary,
    source_sha256: str | None = None,
) -> bool:
    meta = itinerary.conversion_meta
    if meta is None or meta.version != _CONVERSION_VERSION or not meta.quality_passed:
        return True
    if meta.completed_chunk_count != meta.chunk_count:
        return True
    return source_sha256 is not None and meta.source_sha256 != source_sha256


def _document_to_itinerary(
    *,
    source_id: str,
    document: DeepPlanDocument,
    destination: str,
    start_date: DateType | None,
    end_date: DateType | None,
    title: str,
    cache_prefix: str,
    force_rebuild: bool = False,
) -> Itinerary:
    fingerprint = _source_sha256(document.markdown)
    sections = _build_llm_extraction_sections(document.markdown, destination)
    extracted = _extract_report_with_llm(
        markdown=document.markdown,
        destination=destination,
        title=title,
        source_id=source_id,
        cache_prefix=cache_prefix,
        force_rebuild=force_rebuild,
        start_date=start_date,
        end_date=end_date,
    )
    extracted = _validate_extracted_report(
        extracted,
        start_date=start_date,
        end_date=end_date,
    )
    return _itinerary_from_extracted_report(
        source_id=source_id,
        source_sha256=fingerprint,
        extracted=extracted,
        destination=destination,
        title=title,
        cache_prefix=cache_prefix,
        chunk_count=len(sections),
    )


class ReportItineraryAgent:
    """Convert a Destination Intelligence Report document into result-page JSON."""

    def convert_document_to_itinerary(
        self,
        *,
        source_id: str,
        document: DeepPlanDocument,
        destination: str,
        start_date: DateType | None,
        end_date: DateType | None,
        title: str,
        cache_prefix: str,
        force_rebuild: bool = False,
    ) -> Itinerary:
        return _document_to_itinerary(
            source_id=source_id,
            document=document,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            title=title,
            cache_prefix=cache_prefix,
            force_rebuild=force_rebuild,
        )


def convert_document_to_itinerary(
    *,
    source_id: str,
    document: DeepPlanDocument,
    destination: str,
    start_date: DateType | None,
    end_date: DateType | None,
    title: str,
    cache_prefix: str,
    force_rebuild: bool = False,
) -> Itinerary:
    return ReportItineraryAgent().convert_document_to_itinerary(
        source_id=source_id,
        document=document,
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        title=title,
        cache_prefix=cache_prefix,
        force_rebuild=force_rebuild,
    )


__all__ = [
    "ReportConversionError",
    "ReportConversionIncompleteError",
    "ReportConversionUnavailableError",
    "ReportItineraryAgent",
    "convert_document_to_itinerary",
    "_ExtractedDay",
    "_ExtractedMeal",
    "_ExtractedReport",
    "_ExtractedSpot",
    "_ReportExtractionSection",
    "_build_llm_extraction_sections",
    "_cache_trip_id",
    "_document_to_itinerary",
    "_extract_report_section_with_llm",
    "_extract_report_with_llm",
    "_extracted_report_json_path",
    "_load_extracted_report_json",
    "_maybe_enrich_itinerary_with_map_data",
    "_needs_rebuild_from_cache",
    "_parse_date",
    "_save_extracted_report_json",
    "_source_sha256",
    "_validate_extracted_report",
]
