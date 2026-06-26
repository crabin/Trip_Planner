from __future__ import annotations

from datetime import date as DateType
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.models.schemas import Itinerary
from app.services.storage_service import DeepPlanDocument


class ReportItineraryGraphState(TypedDict, total=False):
    source_id: str
    document: DeepPlanDocument
    destination: str
    start_date: DateType | None
    end_date: DateType | None
    title: str
    cache_prefix: str
    force_rebuild: bool
    itinerary: Itinerary


def run_report_itinerary_graph(
    converter: Any,
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
    graph = StateGraph(ReportItineraryGraphState)
    graph.add_node("convert", lambda state: _convert(converter, state))
    graph.set_entry_point("convert")
    graph.add_edge("convert", END)
    result = graph.compile().invoke(
        {
            "source_id": source_id,
            "document": document,
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "title": title,
            "cache_prefix": cache_prefix,
            "force_rebuild": force_rebuild,
        }
    )
    return result["itinerary"]


def _convert(converter: Any, state: ReportItineraryGraphState) -> ReportItineraryGraphState:
    return {
        "itinerary": converter(
            source_id=state["source_id"],
            document=state["document"],
            destination=state["destination"],
            start_date=state.get("start_date"),
            end_date=state.get("end_date"),
            title=state["title"],
            cache_prefix=state["cache_prefix"],
            force_rebuild=state.get("force_rebuild", False),
        )
    }
