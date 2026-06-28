from __future__ import annotations

from typing import Any

from app.models.schemas import (
    DeepPlanDocument,
    DeepPlanResearchTraceStep,
    DeepPlanSource,
    TripRequest,
)
from app.services.storage_service import (
    complete_deep_plan,
    fail_deep_plan,
    update_deep_plan_progress,
)
from app.services.report_catalog_service import REPORT_DIR

def build_deep_planning_query(request: TripRequest) -> str:
    """把规划页的全部结构化字段整合成 destination agent 的旅行需求。"""
    preferences = "、".join(request.preferences) or "无特别偏好"
    dietary = "、".join(request.dietary_preferences) or "无特别忌口"
    return "\n".join(
        [
            f"目的地：{request.destination}",
            f"出行日期：{request.start_date.isoformat()} 至 {request.end_date.isoformat()}",
            f"同行人数：{request.travelers} 人",
            f"总预算：{request.budget:g}",
            f"旅行偏好：{preferences}",
            f"节奏偏好：{request.pace or '适中'}",
            f"住宿偏好：{request.hotel_level or '未指定'}",
            f"饮食偏好：{dietary}",
            f"额外要求：{request.special_notes or '无'}",
            "请生成与以上日期、预算和同行需求一致的完整可执行旅行攻略。",
        ]
    )


def _collect_sources(agent: Any) -> list[DeepPlanSource]:
    sources: list[DeepPlanSource] = []
    for paragraph in agent.state.paragraphs:
        for search in paragraph.research.search_history:
            sources.append(
                DeepPlanSource(
                    section_title=paragraph.title,
                    query=search.query,
                    step_id=getattr(search, "step_id", ""),
                    title=search.title,
                    url=search.url,
                    content=search.content,
                    raw_content=getattr(search, "raw_content", None),
                    used_in_summary=bool(getattr(search, "used_in_summary", False)),
                    score=search.score,
                    published_date=search.published_date,
                )
            )
    return sources


def _collect_research_trace(agent: Any) -> list[DeepPlanResearchTraceStep]:
    trace: list[DeepPlanResearchTraceStep] = []
    for paragraph in agent.state.paragraphs:
        research = getattr(paragraph, "research", None)
        for step in getattr(research, "trace_steps", []) or []:
            trace.append(
                DeepPlanResearchTraceStep(
                    step_id=getattr(step, "step_id", ""),
                    phase=getattr(step, "phase", ""),
                    section_title=getattr(step, "section_title", "") or paragraph.title,
                    search_query=getattr(step, "search_query", ""),
                    search_tool=getattr(step, "search_tool", ""),
                    reasoning=getattr(step, "reasoning", ""),
                    summary_before=getattr(step, "summary_before", ""),
                    summary_after=getattr(step, "summary_after", ""),
                    evidence_count=getattr(step, "evidence_count", 0),
                    prompt_chars=getattr(step, "prompt_chars", 0),
                    estimated_prompt_tokens=getattr(step, "estimated_prompt_tokens", 0),
                    fallback_reason=getattr(step, "fallback_reason", ""),
                    timestamp=getattr(step, "timestamp", ""),
                )
            )
    return trace


def run_deep_planning_job(trip_id: str, request: TripRequest) -> None:
    """后台执行一次独立的深度规划并持久化终态。"""
    try:
        from app.agents.destination_intelligence_agent import (
            DestinationIntelligenceAgent,
            Settings,
        )

        agent = DestinationIntelligenceAgent(
            Settings(
                OUTPUT_DIR=str(REPORT_DIR),
                MAX_REFLECTIONS=request.deep_planning_reflection_rounds,
                DEEP_PLANNING_SEARCH_ENGINE=request.deep_planning_search_engine,
            )
        )

        def report_progress(progress: int, message: str) -> None:
            update_deep_plan_progress(trip_id, progress, message)

        markdown = agent.research(
            build_deep_planning_query(request),
            save_report=True,
            progress_callback=report_progress,
        )
        complete_deep_plan(
            trip_id,
            DeepPlanDocument(
                markdown=markdown,
                sources=_collect_sources(agent),
                research_trace=_collect_research_trace(agent),
            ),
        )
    except Exception as exc:
        fail_deep_plan(trip_id, str(exc) or exc.__class__.__name__)
