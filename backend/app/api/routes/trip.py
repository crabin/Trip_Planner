from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from app.models.schemas import (
    Itinerary,
    TripDetailResponse,
    TripEditRequest,
    TripListResponse,
    TripRequest,
    TripSaveRequest,
    TripSummaryItem,
)
from app.services.deep_planning_service import run_deep_planning_job
from app.services.report_catalog_service import (
    delete_report_artifact,
    get_report_artifact,
    report_artifact_to_detail,
)
from app.services.report_itinerary_service import (
    get_or_create_deep_plan_itinerary,
    get_or_create_report_itinerary,
)
from app.agents.report_itinerary_agent.agent import ReportConversionError
from app.services.storage_service import (
    create_deep_plan,
    delete_trip_by_trip_id,
    get_itinerary_by_trip_id,
    list_saved_itineraries,
    save_itinerary,
)
from app.services.trip_service import edit_trip_itinerary, generate_trip_itinerary


router = APIRouter(prefix="/trip", tags=["trip"])


@router.get("", response_model=TripListResponse)
def list_trips() -> TripListResponse:
    """返回已保存行程的摘要列表。"""
    return list_saved_itineraries()


@router.post("/generate", response_model=Itinerary)
def generate_trip(request: TripRequest) -> Itinerary:
    """生成结构化 itinerary。"""
    return generate_trip_itinerary(request)


@router.post(
    "/deep-generate",
    response_model=TripSummaryItem,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_deep_trip(
    request: TripRequest,
    background_tasks: BackgroundTasks,
) -> TripSummaryItem:
    """先创建历史记录，再在后台执行耗时的目的地深度研究。"""
    item = create_deep_plan(request)
    background_tasks.add_task(run_deep_planning_job, item.trip_id, request)
    return item


@router.post("/edit", response_model=Itinerary)
def edit_trip(request: TripEditRequest) -> Itinerary:
    """根据用户编辑指令返回更新后的 itinerary。"""
    return edit_trip_itinerary(request)


@router.get("/reports/{report_id}", response_model=TripDetailResponse)
def get_report_detail(report_id: str) -> TripDetailResponse:
    """把历史 Markdown/State Report 转为前端可消费的 JSON 详情。"""
    artifact = get_report_artifact(report_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report_artifact_to_detail(artifact)


@router.get("/reports/{report_id}/itinerary", response_model=Itinerary)
def get_report_itinerary(
    report_id: str,
    force: bool = Query(default=False, description="是否跳过缓存并重新从 Report 转换"),
) -> Itinerary:
    """把历史 Report 转换为结果页使用的结构化 itinerary；已转换则直接复用。"""
    try:
        itinerary = get_or_create_report_itinerary(report_id, force_rebuild=force)
    except ReportConversionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    if itinerary is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return itinerary


@router.get("/reports/{report_id}/markdown", response_class=PlainTextResponse)
def get_report_markdown(report_id: str) -> PlainTextResponse:
    """直接查看原始 Markdown Report。"""
    artifact = get_report_artifact(report_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return PlainTextResponse(
        artifact.document.markdown,
        media_type="text/markdown; charset=utf-8",
    )


@router.post("/save")
def save_trip(request: TripSaveRequest) -> dict[str, str]:
    """保存 itinerary，并返回 trip_id。"""
    if request.trip_id != request.itinerary.trip_id:
        raise HTTPException(status_code=400, detail="Trip ID mismatch.")

    saved_trip_id = save_itinerary(request.itinerary)
    return {
        "message": "Trip itinerary saved successfully.",
        "trip_id": saved_trip_id,
    }


@router.get("/{trip_id}", response_model=TripDetailResponse)
def get_trip_detail(trip_id: str) -> TripDetailResponse:
    """根据 trip_id 查询已保存 itinerary。"""
    trip_detail = get_itinerary_by_trip_id(trip_id)
    if trip_detail is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    if trip_detail.status == "generating":
        raise HTTPException(status_code=409, detail="Deep planning is still generating.")
    if trip_detail.status == "failed":
        raise HTTPException(status_code=409, detail="Deep planning failed.")
    return trip_detail


@router.get("/{trip_id}/deep-itinerary", response_model=Itinerary)
def get_deep_plan_itinerary(
    trip_id: str,
    force: bool = Query(default=False, description="是否跳过缓存并重新从深度规划文档转换"),
) -> Itinerary:
    """把已完成深度规划文档转换为结果页使用的结构化 itinerary；已转换则直接复用。"""
    try:
        itinerary = get_or_create_deep_plan_itinerary(trip_id, force_rebuild=force)
    except ReportConversionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    if itinerary is None:
        raise HTTPException(status_code=404, detail="Deep plan not found or not completed.")
    return itinerary


@router.delete("/{trip_id}")
def delete_trip(trip_id: str) -> dict[str, str]:
    """根据 trip_id 删除已保存 itinerary。"""
    summary = next(
        (item for item in list_saved_itineraries().items if item.trip_id == trip_id),
        None,
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    if summary.status == "generating":
        raise HTTPException(status_code=409, detail="Generating deep plans cannot be deleted.")

    result = delete_trip_by_trip_id(trip_id)
    if result == "generating":
        raise HTTPException(status_code=409, detail="Generating deep plans cannot be deleted.")
    if summary.is_report_only and summary.report_id is not None:
        delete_report_artifact(summary.report_id)
    if result == "not_found" and not summary.is_report_only:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return {
        "message": "Trip itinerary deleted successfully.",
        "trip_id": trip_id,
    }
