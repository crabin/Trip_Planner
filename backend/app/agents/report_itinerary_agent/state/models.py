from __future__ import annotations

from dataclasses import dataclass
from datetime import date as DateType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class ReportDayDraft:
    """Legacy compatibility model retained for callers outside the v2 pipeline."""

    day_index: int
    date: DateType | None
    theme: str
    body: str
    spot_names: tuple[str, ...]
    meal_names: tuple[str, ...]
    hotel_name: str | None


class ValidatedExtractionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ExtractedOverviewFact(ValidatedExtractionModel):
    key: str = Field(..., description="稳定字段 key，例如 date_range、travelers、pace")
    label: str = Field(..., description="结果页展示标签")
    value: str = Field(..., description="只来自 Report 的字段值")
    source_chunk_ids: list[str] = Field(default_factory=list)


class ExtractedSpot(ValidatedExtractionModel):
    name: str = Field(..., description="结果页展示的真实地点名")
    map_query: str = Field(default="", description="给地图检索的精确关键词")
    description: str = Field(default="", description="来自 Report 的地点说明")
    start_time: str | None = Field(default=None, description="Report 明确给出的开始时间")
    end_time: str | None = Field(default=None, description="Report 明确给出的结束时间")
    estimated_cost: float | None = Field(default=None, ge=0, description="Report 明确给出的费用")


class ExtractedMeal(ValidatedExtractionModel):
    name: str = Field(..., description="餐厅名、菜系或餐饮区域")
    meal_type: str = Field(default="餐饮")
    map_query: str = Field(default="", description="给地图/本地生活检索的关键词")
    notes: str = Field(default="", description="来自 Report 的餐饮说明")
    estimated_cost: float | None = Field(default=None, ge=0, description="Report 明确给出的费用")


class ExtractedTransport(ValidatedExtractionModel):
    mode: str = Field(..., description="交通方式")
    from_place: str | None = None
    to_place: str | None = None
    duration: str | None = None
    estimated_cost: float | None = Field(default=None, ge=0)


class ExtractedDay(ValidatedExtractionModel):
    day_index: int = Field(..., ge=1)
    date: str | None = None
    theme: str = ""
    full_day_text: str = Field(default="", description="该日完整可读行程内容")
    spots: list[ExtractedSpot] = Field(default_factory=list)
    meals: list[ExtractedMeal] = Field(default_factory=list)
    hotel_name: str = ""
    hotel_query: str = ""
    hotel_level: str = ""
    hotel_cost: float | None = Field(default=None, ge=0)
    transport_note: str = ""
    transport: list[ExtractedTransport] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)


class ExtractedReport(ValidatedExtractionModel):
    overview: str = Field(default="", description="结果页行程概览")
    overview_facts: list[ExtractedOverviewFact] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    total_days: int | None = Field(default=None, ge=1)
    total_budget: float = Field(default=0.0, ge=0)
    tips: list[str] = Field(default_factory=list)
    days: list[ExtractedDay] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ReportExtractionSection:
    section_id: str
    section_type: str
    title: str
    markdown: str
    heading_path: tuple[str, ...] = ()
    order: int = 0


class ChunkExtraction(ValidatedExtractionModel):
    chunk_id: str
    section_kind: Literal[
        "overview",
        "day",
        "transport",
        "lodging",
        "dining",
        "budget",
        "tips",
        "poi_pool",
        "checklist",
        "sources",
        "other",
    ] = "other"
    extracted: ExtractedReport = Field(default_factory=ExtractedReport)


class ChunkExtractionBatch(ValidatedExtractionModel):
    extractions: list[ChunkExtraction] = Field(default_factory=list)
