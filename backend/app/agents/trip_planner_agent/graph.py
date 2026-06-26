from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.models.schemas import DayPlan, TripEditRequest, TripRequest

from .llms import LLMSettings
from .nodes.generation import generate_day_edit, generate_trip_draft
from .prompts import build_day_edit_messages, build_planner_messages
from .state import DayEditDraft, PlannerDraft


class PlannerGraphState(TypedDict, total=False):
    mode: Literal["plan", "edit"]
    request: TripRequest | TripEditRequest
    target_day: DayPlan
    rag_contexts: list[str]
    day_count: int
    settings: LLMSettings
    llm: Any | None
    messages: list[tuple[str, str]]
    planner_result: PlannerDraft | None
    edit_result: DayEditDraft | None


def run_planner_graph(
    *,
    request: TripRequest,
    rag_contexts: list[str],
    day_count: int,
    settings: LLMSettings,
    llm_factory,
) -> PlannerDraft | None:
    graph = _build_graph(llm_factory)
    result = graph.invoke(
        {
            "mode": "plan",
            "request": request,
            "rag_contexts": rag_contexts,
            "day_count": day_count,
            "settings": settings,
        }
    )
    return result.get("planner_result")


def run_day_edit_graph(
    *,
    request: TripEditRequest,
    target_day: DayPlan,
    settings: LLMSettings,
    llm_factory,
) -> DayEditDraft | None:
    graph = _build_graph(llm_factory)
    result = graph.invoke(
        {
            "mode": "edit",
            "request": request,
            "target_day": target_day,
            "settings": settings,
        }
    )
    return result.get("edit_result")


def _build_graph(llm_factory):
    graph = StateGraph(PlannerGraphState)
    graph.add_node("prepare_llm", lambda state: _prepare_llm(state, llm_factory))
    graph.add_node("build_messages", _build_messages)
    graph.add_node("invoke_model", _invoke_model)
    graph.set_entry_point("prepare_llm")
    graph.add_conditional_edges(
        "prepare_llm",
        lambda state: "done" if state.get("llm") is None else "messages",
        {"done": END, "messages": "build_messages"},
    )
    graph.add_edge("build_messages", "invoke_model")
    graph.add_edge("invoke_model", END)
    return graph.compile()


def _prepare_llm(state: PlannerGraphState, llm_factory) -> PlannerGraphState:
    llm = llm_factory(state["settings"])
    return {"llm": llm}


def _build_messages(state: PlannerGraphState) -> PlannerGraphState:
    if state["mode"] == "plan":
        return {
            "messages": build_planner_messages(
                state["request"],
                state.get("rag_contexts", []),
                state["day_count"],
            )
        }
    return {
        "messages": build_day_edit_messages(
            state["request"],
            state["target_day"],
        )
    }


def _invoke_model(state: PlannerGraphState) -> PlannerGraphState:
    llm = state.get("llm")
    if llm is None:
        return {"planner_result": None, "edit_result": None}
    if state["mode"] == "plan":
        return {
            "planner_result": generate_trip_draft(
                llm,
                state["messages"],
                state["day_count"],
            )
        }
    return {"edit_result": generate_day_edit(llm, state["messages"])}
