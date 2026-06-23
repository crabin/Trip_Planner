from __future__ import annotations

from datetime import date as DateType

from app.agents.report_itinerary_agent import agent as report_itinerary_agent
from app.agents.report_itinerary_agent.agent import (
    _ExtractedDay,
    _ExtractedMeal,
    _ExtractedReport,
    _ExtractedSpot,
    _ReportExtractionSection,
    _build_llm_extraction_sections,
    _cache_trip_id,
    _extract_report_section_with_llm,
    _extract_report_with_llm,
    _extracted_report_json_path,
    _load_extracted_report_json,
    _maybe_enrich_itinerary_with_map_data,
    _needs_rebuild_from_cache,
    _parse_date,
    _save_extracted_report_json,
    _source_sha256,
    build_chat_llm,
)
from app.models.schemas import DeepPlanDocument, Itinerary
from app.services.report_catalog_service import get_report_artifact
from app.services.storage_service import (
    get_itinerary_by_trip_id,
    save_itinerary,
)


def _sync_agent_compatibility_hooks() -> None:
    """Apply service-level monkeypatch hooks to the agent module before conversion."""
    report_itinerary_agent.build_chat_llm = build_chat_llm
    report_itinerary_agent._extract_report_with_llm = _extract_report_with_llm
    report_itinerary_agent._extract_report_section_with_llm = _extract_report_section_with_llm
    report_itinerary_agent._save_extracted_report_json = _save_extracted_report_json
    report_itinerary_agent._maybe_enrich_itinerary_with_map_data = _maybe_enrich_itinerary_with_map_data


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
    _sync_agent_compatibility_hooks()
    return report_itinerary_agent.convert_document_to_itinerary(
        source_id=source_id,
        document=document,
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        title=title,
        cache_prefix=cache_prefix,
        force_rebuild=force_rebuild,
    )


def _agent_needs_rebuild_from_cache(itinerary: Itinerary, source_sha256: str) -> bool:
    _sync_agent_compatibility_hooks()
    return report_itinerary_agent._needs_rebuild_from_cache(itinerary, source_sha256)


def get_or_create_report_itinerary(
    report_id: str,
    *,
    force_rebuild: bool = False,
) -> Itinerary | None:
    """读取或生成基于历史 Report 的结构化结果页 itinerary。"""
    artifact = get_report_artifact(report_id)
    if artifact is None:
        return None

    fingerprint = _source_sha256(artifact.document.markdown)
    cache_id = _cache_trip_id("report_itinerary", report_id)
    cached_detail = get_itinerary_by_trip_id(cache_id)
    if (
        not force_rebuild
        and cached_detail
        and cached_detail.itinerary
        and not _agent_needs_rebuild_from_cache(cached_detail.itinerary, fingerprint)
    ):
        return cached_detail.itinerary

    itinerary = _document_to_itinerary(
        source_id=report_id,
        document=artifact.document,
        destination=artifact.destination,
        start_date=_parse_date(artifact.dates[0] if artifact.dates else None),
        end_date=_parse_date(artifact.dates[1] if len(artifact.dates) >= 2 else None),
        title=artifact.title or artifact.query,
        cache_prefix="report_itinerary",
        force_rebuild=force_rebuild,
    )
    save_itinerary(itinerary)
    return itinerary


def get_or_create_deep_plan_itinerary(
    trip_id: str,
    *,
    force_rebuild: bool = False,
) -> Itinerary | None:
    """读取或生成基于已完成深度规划文档的结构化结果页 itinerary。"""
    detail = get_itinerary_by_trip_id(trip_id)
    if detail is None or detail.status != "completed":
        return None
    if detail.itinerary is not None:
        return detail.itinerary
    if detail.deep_plan is None:
        return None

    fingerprint = _source_sha256(detail.deep_plan.markdown)
    cache_id = _cache_trip_id("deep_itinerary", trip_id)
    cached_detail = get_itinerary_by_trip_id(cache_id)
    if (
        not force_rebuild
        and cached_detail
        and cached_detail.itinerary
        and not _agent_needs_rebuild_from_cache(cached_detail.itinerary, fingerprint)
    ):
        return cached_detail.itinerary

    itinerary = _document_to_itinerary(
        source_id=trip_id,
        document=detail.deep_plan,
        destination=detail.display_title.split("·", maxsplit=1)[0].strip() or detail.detail_title,
        start_date=_parse_date(str(detail.start_date) if detail.start_date else None),
        end_date=_parse_date(str(detail.end_date) if detail.end_date else None),
        title=detail.detail_title or detail.display_title,
        cache_prefix="deep_itinerary",
        force_rebuild=force_rebuild,
    )
    save_itinerary(itinerary)
    return itinerary


__all__ = [
    "get_or_create_deep_plan_itinerary",
    "get_or_create_report_itinerary",
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
    "build_chat_llm",
]
