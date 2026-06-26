from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .state import State


class DestinationGraphState(TypedDict, total=False):
    query: str
    save_report: bool
    notify: Callable[[int, str], None]
    final_report: str
    state: State


def run_destination_research_graph(
    agent: Any,
    *,
    query: str,
    save_report: bool,
    notify: Callable[[int, str], None],
) -> str:
    graph = StateGraph(DestinationGraphState)
    graph.add_node("prepare", lambda state: _prepare(agent, state))
    graph.add_node("structure", lambda state: _structure(agent, state))
    graph.add_node("paragraphs", lambda state: _paragraphs(agent, state))
    graph.add_node("format_report", lambda state: _format_report(agent, state))
    graph.add_node("save", lambda state: _save(agent, state))
    graph.set_entry_point("prepare")
    graph.add_edge("prepare", "structure")
    graph.add_edge("structure", "paragraphs")
    graph.add_edge("paragraphs", "format_report")
    graph.add_edge("format_report", "save")
    graph.add_edge("save", END)
    result = graph.compile().invoke(
        {
            "query": query,
            "save_report": save_report,
            "notify": notify,
        }
    )
    return result["final_report"]


def _prepare(agent: Any, state: DestinationGraphState) -> DestinationGraphState:
    state["notify"](5, "正在准备深度研究")
    agent.state = State(query=state["query"])
    return {"state": agent.state}


def _structure(agent: Any, state: DestinationGraphState) -> DestinationGraphState:
    agent._generate_report_structure(state["query"])
    state["notify"](12, "攻略结构已生成")
    return {"state": agent.state}


def _paragraphs(agent: Any, state: DestinationGraphState) -> DestinationGraphState:
    agent._web_progress_callback = state["notify"]
    agent._process_paragraphs()
    return {"state": agent.state}


def _format_report(agent: Any, state: DestinationGraphState) -> DestinationGraphState:
    state["notify"](90, "正在整合完整攻略")
    final_report = agent._generate_final_report()
    return {"final_report": final_report, "state": agent.state}


def _save(agent: Any, state: DestinationGraphState) -> DestinationGraphState:
    final_report = state["final_report"]
    if state["save_report"]:
        agent._save_report(final_report)
    state["notify"](100, "深度规划已完成")
    return {"final_report": final_report, "state": agent.state}
