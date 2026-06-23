import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import inspect, text

from app.config import SessionLocal, engine
from app.models.db_models import TripRecord
from app.models.schemas import (
    DeepPlanDocument,
    Itinerary,
    TripDetailResponse,
    TripListResponse,
    TripRequest,
    TripSummaryItem,
)
from app.services.report_catalog_service import (
    ReportArtifact,
    list_report_artifacts,
    match_report_for_trip,
    report_artifact_to_summary,
)
from app.services.itinerary_display_service import attach_itinerary_display


_ADDITIVE_COLUMNS = {
    "plan_type": "VARCHAR(20) NOT NULL DEFAULT 'quick'",
    "status": "VARCHAR(20) NOT NULL DEFAULT 'completed'",
    "progress": "INTEGER NOT NULL DEFAULT 100",
    "display_title": "TEXT NOT NULL DEFAULT ''",
    "detail_title": "TEXT NOT NULL DEFAULT ''",
    "start_date": "VARCHAR(20)",
    "end_date": "VARCHAR(20)",
    "request_json": "TEXT",
    "deep_plan_json": "TEXT",
    "error_message": "TEXT",
}


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def init_db() -> None:
    """初始化表并为旧版 SQLite 数据库执行安全的增量列迁移。"""
    from app.config import Base

    Base.metadata.create_all(bind=engine)
    existing_columns = {column["name"] for column in inspect(engine).get_columns("trip_records")}
    missing_columns = {
        name: definition
        for name, definition in _ADDITIVE_COLUMNS.items()
        if name not in existing_columns
    }
    if not missing_columns:
        return

    with engine.begin() as connection:
        for name, definition in missing_columns.items():
            connection.execute(text(f"ALTER TABLE trip_records ADD COLUMN {name} {definition}"))


def _record_date_range(record: TripRecord) -> tuple[str | None, str | None]:
    if record.start_date and record.end_date:
        return record.start_date, record.end_date
    try:
        itinerary_data = json.loads(record.itinerary_json)
    except (TypeError, json.JSONDecodeError):
        return None, None
    days = itinerary_data.get("days", []) if isinstance(itinerary_data, dict) else []
    dates = [str(day.get("date")) for day in days if isinstance(day, dict) and day.get("date")]
    return (dates[0], dates[-1]) if dates else (None, None)


def _build_record_detail_title(
    record: TripRecord,
    start_date: str | None,
    end_date: str | None,
) -> str:
    stored_detail = (record.detail_title or "").strip()
    summary = (record.summary or "").strip()
    if stored_detail and stored_detail != summary:
        return stored_detail

    parts: list[str] = []
    if start_date and end_date:
        parts.append(f"{start_date} 至 {end_date}")
    elif start_date:
        parts.append(start_date)

    parts.append("深度规划" if (record.plan_type or "quick") == "deep" else "快速规划")
    status_text = {
        "generating": "正在生成",
        "failed": "生成失败",
        "completed": "已完成",
    }.get(record.status or "completed", "已完成")
    parts.append(status_text)
    return " · ".join(parts)


def _summary_from_record(
    record: TripRecord,
    report: ReportArtifact | None = None,
) -> TripSummaryItem:
    start_date, end_date = _record_date_range(record)
    display_title = record.display_title or record.destination
    if not record.display_title and start_date and end_date:
        display_title = f"{record.destination} · {start_date} → {end_date}"
    plan_type = record.plan_type or "quick"
    status = record.status or "completed"
    has_itinerary = plan_type == "quick" and bool(record.itinerary_json)
    has_deep_detail = plan_type == "deep" and bool(record.deep_plan_json)
    return TripSummaryItem(
        trip_id=record.trip_id,
        destination=record.destination,
        summary=record.summary,
        plan_type=plan_type,
        status=status,
        progress=record.progress if record.progress is not None else 100,
        display_title=display_title,
        detail_title=_build_record_detail_title(record, start_date, end_date),
        start_date=start_date,
        end_date=end_date,
        error_message=record.error_message,
        has_detail=status == "completed" and (has_itinerary or has_deep_detail or report is not None),
        has_itinerary=has_itinerary,
        has_report=report is not None,
        report_id=report.report_id if report is not None else None,
        is_report_only=False,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _is_internal_itinerary_cache(record: TripRecord) -> bool:
    return record.trip_id.startswith(("report_itinerary_", "deep_itinerary_"))


def save_itinerary(itinerary: Itinerary) -> str:
    """保存或更新完整 itinerary，并返回 trip_id。"""
    init_db()
    attach_itinerary_display(itinerary)
    session = SessionLocal()
    try:
        itinerary_json = json.dumps(itinerary.model_dump(mode="json"), ensure_ascii=False)
        existing_record = session.query(TripRecord).filter(TripRecord.trip_id == itinerary.trip_id).first()

        itinerary_dates = [day.date.isoformat() for day in itinerary.days if day.date is not None]
        start_date = itinerary_dates[0] if itinerary_dates else None
        end_date = itinerary_dates[-1] if itinerary_dates else None
        detail_title = " · ".join(
            part
            for part in [
                f"{start_date} 至 {end_date}" if start_date and end_date else start_date,
                "快速规划",
                "已完成",
            ]
            if part
        )

        if existing_record is None:
            record = TripRecord(
                trip_id=itinerary.trip_id,
                destination=itinerary.destination,
                summary=itinerary.summary,
                plan_type="quick",
                status="completed",
                progress=100,
                display_title=itinerary.destination,
                detail_title=detail_title,
                start_date=start_date,
                end_date=end_date,
                itinerary_json=itinerary_json,
            )
            session.add(record)
        else:
            existing_record.destination = itinerary.destination
            existing_record.summary = itinerary.summary
            existing_record.plan_type = "quick"
            existing_record.status = "completed"
            existing_record.progress = 100
            existing_record.display_title = itinerary.destination
            existing_record.detail_title = detail_title
            existing_record.start_date = start_date
            existing_record.end_date = end_date
            existing_record.itinerary_json = itinerary_json
            existing_record.deep_plan_json = None
            existing_record.error_message = None

        session.commit()
        return itinerary.trip_id
    finally:
        session.close()


def create_deep_plan(request: TripRequest) -> TripSummaryItem:
    """在执行耗时研究前先创建可见的深度规划历史记录。"""
    init_db()
    day_count = max((request.end_date - request.start_date).days + 1, 1)
    trip_id = f"deep_{uuid4().hex}"
    display_title = (
        f"{request.destination} · {request.start_date.isoformat()} → {request.end_date.isoformat()}"
    )
    detail_title = (
        f"{request.destination} {day_count}日深度旅行攻略｜"
        f"{request.travelers}人 · {request.pace or '适中'}节奏"
    )
    session = SessionLocal()
    try:
        record = TripRecord(
            trip_id=trip_id,
            destination=request.destination,
            summary="深度规划正在生成，请稍候查看进度。",
            plan_type="deep",
            status="generating",
            progress=3,
            display_title=display_title,
            detail_title=detail_title,
            start_date=request.start_date.isoformat(),
            end_date=request.end_date.isoformat(),
            request_json=json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
            itinerary_json="{}",
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return _summary_from_record(record)
    finally:
        session.close()


def update_deep_plan_progress(trip_id: str, progress: int, message: str) -> None:
    """更新仍在生成中的深度规划进度。"""
    init_db()
    session = SessionLocal()
    try:
        record = session.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if record is None or record.plan_type != "deep" or record.status != "generating":
            return
        record.progress = min(max(progress, record.progress or 0), 99)
        record.summary = message
        record.updated_at = _utcnow_naive()
        session.commit()
    finally:
        session.close()


def complete_deep_plan(trip_id: str, document: DeepPlanDocument) -> None:
    """原子写入深度规划文档并把任务切换为完成状态。"""
    init_db()
    session = SessionLocal()
    try:
        record = session.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if record is None or record.plan_type != "deep":
            return
        record.deep_plan_json = json.dumps(document.model_dump(mode="json"), ensure_ascii=False)
        record.status = "completed"
        record.progress = 100
        record.summary = f"深度攻略已生成，包含 {len(document.sources)} 条研究来源。"
        record.error_message = None
        record.updated_at = _utcnow_naive()
        session.commit()
    finally:
        session.close()


def fail_deep_plan(trip_id: str, error_message: str) -> None:
    """记录后台深度规划失败，避免历史卡片永久停留在生成中。"""
    init_db()
    session = SessionLocal()
    try:
        record = session.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if record is None or record.plan_type != "deep":
            return
        record.status = "failed"
        record.summary = "深度规划生成失败，可删除后重新提交。"
        record.error_message = error_message[:500]
        record.updated_at = _utcnow_naive()
        session.commit()
    finally:
        session.close()


def get_itinerary_by_trip_id(trip_id: str) -> TripDetailResponse | None:
    """读取快速 itinerary 或已生成的深度规划文档。"""
    init_db()
    session = SessionLocal()
    try:
        record = session.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if record is None:
            return None

        itinerary = None
        deep_plan = None
        if (record.plan_type or "quick") == "quick":
            itinerary = Itinerary(**json.loads(record.itinerary_json))
            attach_itinerary_display(itinerary)
        elif record.deep_plan_json:
            deep_plan = DeepPlanDocument(**json.loads(record.deep_plan_json))

        start_date, end_date = _record_date_range(record)

        return TripDetailResponse(
            trip_id=record.trip_id,
            plan_type=record.plan_type or "quick",
            status=record.status or "completed",
            progress=record.progress if record.progress is not None else 100,
            display_title=record.display_title or record.destination,
            detail_title=_build_record_detail_title(
                record,
                start_date,
                end_date,
            ),
            start_date=start_date,
            end_date=end_date,
            itinerary=itinerary,
            deep_plan=deep_plan,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    finally:
        session.close()


def list_saved_itineraries() -> TripListResponse:
    """返回快速行程和深度规划任务的统一摘要列表。"""
    init_db()
    session = SessionLocal()
    try:
        records = session.query(TripRecord).order_by(
            TripRecord.updated_at.desc(),
            TripRecord.id.desc(),
        ).all()
        artifacts = list_report_artifacts()
        used_report_ids: set[str] = set()
        items: list[TripSummaryItem] = []
        for record in records:
            if _is_internal_itinerary_cache(record):
                continue
            start_date, end_date = _record_date_range(record)
            report = match_report_for_trip(
                record.destination,
                start_date,
                end_date,
                artifacts,
                used_report_ids,
            )
            if report is not None:
                used_report_ids.add(report.report_id)
            items.append(_summary_from_record(record, report))

        items.extend(
            report_artifact_to_summary(artifact)
            for artifact in artifacts
            if artifact.report_id not in used_report_ids
        )
        items.sort(
            key=lambda item: item.updated_at or item.created_at or datetime.min,
            reverse=True,
        )
        return TripListResponse(total=len(items), items=items)
    finally:
        session.close()


def delete_trip_by_trip_id(
    trip_id: str,
) -> Literal["deleted", "generating", "not_found"]:
    """删除终态记录；生成中的深度规划不可删除。"""
    init_db()
    session = SessionLocal()
    try:
        record = session.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if record is None:
            return "not_found"
        if record.plan_type == "deep" and record.status == "generating":
            return "generating"
        session.delete(record)
        session.commit()
        return "deleted"
    finally:
        session.close()


def delete_itinerary_by_trip_id(trip_id: str) -> bool:
    """保留旧存储 API：仅在记录确实删除时返回 True。"""
    return delete_trip_by_trip_id(trip_id) == "deleted"
