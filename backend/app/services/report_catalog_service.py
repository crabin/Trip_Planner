from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable

from app.models.schemas import (
    DeepPlanDocument,
    DeepPlanResearchTraceStep,
    DeepPlanSource,
    TripDetailResponse,
    TripSummaryItem,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPORT_DIR = BACKEND_DIR / "destination_intelligence_streamlit_reports"
_FULL_DATE_PATTERN = re.compile(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})")
_TIMESTAMP_SUFFIX = re.compile(r"_\d{8}_\d{6}(?:_\d{6})?$")


@dataclass(frozen=True)
class ReportArtifact:
    report_id: str
    markdown_path: Path
    state_path: Path | None
    title: str
    query: str
    destination: str
    dates: tuple[str, ...]
    document: DeepPlanDocument
    created_at: datetime
    updated_at: datetime


def _first_heading(markdown: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else "历史深度旅行 Report"


def _fallback_query_from_filename(path: Path) -> str:
    stem = path.stem
    for prefix in ("travel_guide_", "deep_search_report_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
            break
    return _TIMESTAMP_SUFFIX.sub("", stem).replace("_", " ").strip()


def _read_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file() or path.stat().st_size == 0:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _paired_state_path(markdown_path: Path) -> Path | None:
    if not markdown_path.name.startswith("travel_guide_"):
        return None
    candidate = markdown_path.with_name(
        f"state_{markdown_path.name.removeprefix('travel_guide_').removesuffix('.md')}.json"
    )
    return candidate if candidate.exists() else None


def _extract_destination(query: str, title: str, filename_query: str) -> str:
    for text_value, patterns in (
        (query, (r"目的地[：:]\s*([^，,。\n]+)", r"从[^，,。\n]+?去([^，,。\n]+)", r"去([^，,。\n]+)")),
        (filename_query, (r"旅游([^，,。\n]+?)攻略", r"从[^，,。\n]+?去([^，,。\n]+)", r"去([^，,。\n]+)")),
    ):
        for pattern in patterns:
            match = re.search(pattern, text_value)
            if match:
                value = re.split(r"\d|至|到|｜|\|", match.group(1), maxsplit=1)[0].strip()
                if 1 < len(value) <= 30:
                    return value

    title_match = re.search(r"(?:【[^】]+】)?\s*([^\s（(｜|]{2,20})", title)
    return title_match.group(1).strip() if title_match else "深度旅行"


def _extract_dates(*values: str) -> tuple[str, ...]:
    dates: list[str] = []
    for value in values:
        for year, month, day in _FULL_DATE_PATTERN.findall(value):
            normalized = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            if normalized not in dates:
                dates.append(normalized)
    return tuple(dates)


def _parse_datetime(value: Any, fallback_timestamp: float) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_timestamp, UTC).replace(tzinfo=None)


def _sources_from_state(state: dict[str, Any]) -> list[DeepPlanSource]:
    sources: list[DeepPlanSource] = []
    paragraphs = state.get("paragraphs", [])
    if not isinstance(paragraphs, list):
        return sources
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            continue
        section_title = str(paragraph.get("title", ""))
        research = paragraph.get("research", {})
        history = research.get("search_history", []) if isinstance(research, dict) else []
        if not isinstance(history, list):
            continue
        for source in history:
            if not isinstance(source, dict):
                continue
            sources.append(
                DeepPlanSource(
                    section_title=section_title,
                    query=str(source.get("query", "")),
                    step_id=str(source.get("step_id", "")),
                    title=str(source.get("title", "")),
                    url=str(source.get("url", "")),
                    content=str(source.get("content", "")),
                    raw_content=source.get("raw_content"),
                    used_in_summary=bool(source.get("used_in_summary", False)),
                    score=source.get("score"),
                    published_date=source.get("published_date"),
                )
            )
    return sources


def _research_trace_from_state(state: dict[str, Any]) -> list[DeepPlanResearchTraceStep]:
    trace: list[DeepPlanResearchTraceStep] = []
    paragraphs = state.get("paragraphs", [])
    if not isinstance(paragraphs, list):
        return trace
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            continue
        section_title = str(paragraph.get("title", ""))
        research = paragraph.get("research", {})
        steps = research.get("trace_steps", []) if isinstance(research, dict) else []
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            trace.append(
                DeepPlanResearchTraceStep(
                    step_id=str(step.get("step_id", "")),
                    phase=str(step.get("phase", "")),
                    section_title=str(step.get("section_title") or section_title),
                    search_query=str(step.get("search_query", "")),
                    search_tool=str(step.get("search_tool", "")),
                    reasoning=str(step.get("reasoning", "")),
                    summary_before=str(step.get("summary_before", "")),
                    summary_after=str(step.get("summary_after", "")),
                    evidence_count=int(step.get("evidence_count") or 0),
                    prompt_chars=int(step.get("prompt_chars") or 0),
                    estimated_prompt_tokens=int(step.get("estimated_prompt_tokens") or 0),
                    fallback_reason=str(step.get("fallback_reason", "")),
                    timestamp=str(step.get("timestamp", "")),
                )
            )
    return trace


def _build_artifact(markdown_path: Path) -> ReportArtifact | None:
    try:
        markdown = markdown_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if not markdown.strip():
        return None

    state_path = _paired_state_path(markdown_path)
    state = _read_state(state_path)
    filename_query = _fallback_query_from_filename(markdown_path)
    query = str(state.get("query") or filename_query)
    title = str(state.get("report_title") or _first_heading(markdown))
    destination = _extract_destination(query, title, filename_query)
    dates = _extract_dates(query, title, markdown[:5000])
    stat = markdown_path.stat()
    created_at = _parse_datetime(state.get("created_at"), stat.st_mtime)
    updated_at = _parse_datetime(state.get("updated_at"), stat.st_mtime)
    report_id = f"report_{sha256(markdown_path.name.encode('utf-8')).hexdigest()[:20]}"
    return ReportArtifact(
        report_id=report_id,
        markdown_path=markdown_path,
        state_path=state_path,
        title=title,
        query=query,
        destination=destination,
        dates=dates,
        document=DeepPlanDocument(
            markdown=markdown,
            sources=_sources_from_state(state),
            research_trace=_research_trace_from_state(state),
        ),
        created_at=created_at,
        updated_at=updated_at,
    )


def _directory_signature() -> tuple[tuple[str, int, int], ...]:
    if not REPORT_DIR.is_dir():
        return ()
    return tuple(
        sorted(
            (path.name, path.stat().st_mtime_ns, path.stat().st_size)
            for path in REPORT_DIR.iterdir()
            if path.suffix.lower() in {".md", ".json"}
        )
    )


@lru_cache(maxsize=4)
def _load_catalog(signature: tuple[tuple[str, int, int], ...]) -> tuple[ReportArtifact, ...]:
    del signature
    if not REPORT_DIR.is_dir():
        return ()
    artifacts = [
        artifact
        for path in sorted(REPORT_DIR.glob("*.md"))
        if (artifact := _build_artifact(path)) is not None
    ]
    return tuple(sorted(artifacts, key=lambda item: item.updated_at, reverse=True))


def list_report_artifacts() -> tuple[ReportArtifact, ...]:
    return _load_catalog(_directory_signature())


def get_report_artifact(report_id: str) -> ReportArtifact | None:
    return next(
        (artifact for artifact in list_report_artifacts() if artifact.report_id == report_id),
        None,
    )


def match_report_for_trip(
    destination: str,
    start_date: str | None,
    end_date: str | None,
    artifacts: Iterable[ReportArtifact],
    excluded_ids: set[str] | None = None,
) -> ReportArtifact | None:
    normalized_destination = re.sub(r"\s+", "", destination).casefold()
    excluded_ids = excluded_ids or set()
    candidates: list[tuple[int, datetime, ReportArtifact]] = []
    for artifact in artifacts:
        if artifact.report_id in excluded_ids:
            continue
        artifact_destination = re.sub(r"\s+", "", artifact.destination).casefold()
        if artifact_destination != normalized_destination:
            continue
        score = 1
        if start_date and end_date and artifact.dates:
            if start_date in artifact.dates and end_date in artifact.dates:
                score = 3
            elif start_date in artifact.dates or end_date in artifact.dates:
                score = 2
            else:
                continue
        candidates.append((score, artifact.updated_at, artifact))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]


def report_artifact_to_summary(artifact: ReportArtifact) -> TripSummaryItem:
    display_title = artifact.title
    if artifact.destination and len(artifact.dates) >= 2:
        display_title = f"{artifact.destination} · {artifact.dates[0]} → {artifact.dates[1]}"
    return TripSummaryItem(
        trip_id=artifact.report_id,
        destination=artifact.destination,
        summary=f"历史 Report 已加载，包含 {len(artifact.document.sources)} 条研究来源。",
        plan_type="deep",
        status="completed",
        progress=100,
        display_title=display_title,
        detail_title=artifact.title or artifact.query,
        start_date=artifact.dates[0] if artifact.dates else None,
        end_date=artifact.dates[1] if len(artifact.dates) >= 2 else None,
        has_detail=True,
        has_itinerary=False,
        has_report=True,
        report_id=artifact.report_id,
        is_report_only=True,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def report_artifact_to_detail(artifact: ReportArtifact) -> TripDetailResponse:
    summary = report_artifact_to_summary(artifact)
    return TripDetailResponse(
        trip_id=artifact.report_id,
        plan_type="deep",
        status="completed",
        progress=100,
        display_title=summary.display_title,
        detail_title=summary.detail_title,
        start_date=summary.start_date,
        end_date=summary.end_date,
        deep_plan=artifact.document,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def delete_report_artifact(report_id: str) -> bool:
    artifact = get_report_artifact(report_id)
    if artifact is None:
        return False
    artifact.markdown_path.unlink(missing_ok=True)
    if artifact.state_path is not None:
        artifact.state_path.unlink(missing_ok=True)
    _load_catalog.cache_clear()
    return True
