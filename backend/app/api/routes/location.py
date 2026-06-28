from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.location_service import check_destination_span, get_location_suggestions


router = APIRouter(prefix="/location", tags=["location"])


@router.get("/suggestions")
def get_suggestions(
    keyword: str = Query(..., min_length=1, description="城市、区县或地点关键词"),
    limit: int = Query(default=10, ge=1, le=20, description="最大返回数量"),
) -> dict[str, list[dict[str, str]]]:
    """Return remote location suggestions for origin and multi-destination inputs."""
    try:
        return {"items": get_location_suggestions(keyword, limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class DestinationSpanRequest(BaseModel):
    destinations: list[str] = Field(..., min_length=1, max_length=12)


@router.post("/span-check")
def post_span_check(request: DestinationSpanRequest) -> dict:
    """Check whether selected destinations are geographically far apart."""
    try:
        return check_destination_span(request.destinations)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
