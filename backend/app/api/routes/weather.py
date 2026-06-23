from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.weather import WeatherForecastResponse
from app.services.weather_service import get_weather_forecast


router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/forecast", response_model=WeatherForecastResponse)
def get_forecast(city: str = Query(..., description="目的地城市")) -> WeatherForecastResponse:
    """根据城市名称返回天气预报。"""
    try:
        payload = get_weather_forecast(city)
        return WeatherForecastResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
