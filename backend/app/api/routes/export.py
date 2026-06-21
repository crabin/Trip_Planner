from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.models.schemas import Itinerary, TripDetailResponse
from app.services.export_service import itinerary_to_markdown, itinerary_to_pdf_bytes
from app.services.storage_service import get_itinerary_by_trip_id


router = APIRouter(prefix="/export", tags=["export"])


def _build_inline_filename_header(filename: str) -> dict[str, str]:
    """生成兼容中文文件名的响应头。"""
    return {
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
    }


def _build_draft_trip_detail(itinerary: Itinerary) -> TripDetailResponse:
    """构造仅用于导出的行程详情，不把草稿写入历史记录。"""
    return TripDetailResponse(
        trip_id=itinerary.trip_id,
        itinerary=itinerary,
    )


@router.post("/markdown", response_class=PlainTextResponse)
def export_draft_markdown(itinerary: Itinerary) -> PlainTextResponse:
    """直接导出当前草稿，不隐式保存到历史记录。"""
    markdown = itinerary_to_markdown(_build_draft_trip_detail(itinerary))
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=_build_inline_filename_header(f"{itinerary.trip_id}.md"),
    )


@router.post("/pdf", response_class=Response)
def export_draft_pdf(itinerary: Itinerary) -> Response:
    """直接导出当前草稿，不隐式保存到历史记录。"""
    try:
        pdf_bytes = itinerary_to_pdf_bytes(_build_draft_trip_detail(itinerary))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_build_inline_filename_header(f"{itinerary.trip_id}.pdf"),
    )


@router.get("/{trip_id}/markdown", response_class=PlainTextResponse)
def export_trip_markdown(trip_id: str) -> PlainTextResponse:
    """把已保存 itinerary 导出为 Markdown 文本。"""
    trip_detail = get_itinerary_by_trip_id(trip_id)
    if trip_detail is None:
        raise HTTPException(status_code=404, detail="Trip not found.")

    markdown = itinerary_to_markdown(trip_detail)
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=_build_inline_filename_header(f"{trip_id}.md"),
    )


@router.get("/{trip_id}/pdf", response_class=Response)
def export_trip_pdf(trip_id: str) -> Response:
    """把已保存 itinerary 导出为 PDF。"""
    trip_detail = get_itinerary_by_trip_id(trip_id)
    if trip_detail is None:
        raise HTTPException(status_code=404, detail="Trip not found.")

    try:
        pdf_bytes = itinerary_to_pdf_bytes(trip_detail)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_build_inline_filename_header(f"{trip_id}.pdf"),
    )
