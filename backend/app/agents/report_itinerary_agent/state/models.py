from __future__ import annotations

from dataclasses import dataclass
from datetime import date as DateType

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ReportDayDraft:
    day_index: int
    date: DateType | None
    theme: str
    body: str
    spot_names: tuple[str, ...]
    meal_names: tuple[str, ...]
    hotel_name: str | None


class ExtractedSpot(BaseModel):
    name: str = Field(..., description="结果页展示的真实地点名")
    map_query: str = Field(default="", description="给高德地图检索的精确关键词")
    description: str = Field(default="", description="地图点位明细中的说明，来自高德/报告上下文")


class ExtractedMeal(BaseModel):
    name: str = Field(..., description="餐厅名、菜系或餐饮区域")
    meal_type: str = Field(default="餐饮")
    map_query: str = Field(default="", description="给高德地图/本地生活检索的关键词")
    notes: str = Field(default="", description="来自 report 的餐饮说明")


class ExtractedDay(BaseModel):
    day_index: int = Field(..., ge=1)
    date: str | None = None
    theme: str = ""
    full_day_text: str = Field(default="", description="该日完整可读行程内容")
    spots: list[ExtractedSpot] = Field(default_factory=list)
    meals: list[ExtractedMeal] = Field(default_factory=list)
    hotel_name: str = ""
    hotel_query: str = ""
    transport_note: str = ""


class ExtractedReport(BaseModel):
    overview: str = Field(default="", description="结果页行程概览，保留一屏概览格式")
    total_budget: float = Field(default=0.0, ge=0)
    tips: list[str] = Field(default_factory=list)
    days: list[ExtractedDay] = Field(default_factory=list)


@dataclass(frozen=True)
class ReportExtractionSection:
    section_id: str
    section_type: str
    title: str
    markdown: str
