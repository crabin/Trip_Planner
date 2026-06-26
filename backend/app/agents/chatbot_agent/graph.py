from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse

from .state import IntentDecision
from .utils import build_planning_steps, complete_planning_steps


class ChatbotGraphState(TypedDict, total=False):
    request: ChatbotMessageRequest
    decision: IntentDecision
    response: ChatbotMessageResponse
    events: list[dict[str, Any]]


RouteName = Literal["ask", "update", "search", "research"]


def build_chatbot_graph(agent: Any):
    graph = StateGraph(ChatbotGraphState)

    graph.add_node("classify_intent", lambda state: _classify_intent(agent, state))
    graph.add_node("ask", lambda state: _run_ask(agent, state))
    graph.add_node("update", lambda state: _run_update(agent, state))
    graph.add_node("search", lambda state: _run_search(agent, state))
    graph.add_node("research", lambda state: _run_research(agent, state))

    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _route_from_decision,
        {
            "ask": "ask",
            "update": "update",
            "search": "search",
            "research": "research",
        },
    )
    for node_name in ("ask", "update", "search", "research"):
        graph.add_edge(node_name, END)
    return graph.compile()


def _classify_intent(agent: Any, state: ChatbotGraphState) -> ChatbotGraphState:
    request = state["request"]
    decision = agent.intent_node.run(request)
    return {
        "decision": decision,
        "events": [{"event": "intent", "data": decision}],
    }


def _route_from_decision(state: ChatbotGraphState) -> RouteName:
    intent = state["decision"].intent
    if intent in {"update", "personalize"}:
        return "update"
    if intent == "search":
        return "search"
    if intent in {"research", "risk_check", "compare"}:
        return "research"
    return "ask"


def _run_ask(agent: Any, state: ChatbotGraphState) -> ChatbotGraphState:
    plan = build_planning_steps(state["request"], state["decision"])
    response = agent.ask_node.run(state["request"], state["decision"])
    response.research_steps = complete_planning_steps(plan)
    return _final_state(
        {**state, "events": [*state.get("events", []), {"event": "research_plan", "data": plan}]},
        response,
    )


def _run_update(agent: Any, state: ChatbotGraphState) -> ChatbotGraphState:
    plan = build_planning_steps(state["request"], state["decision"])
    response = agent.update_node.run(state["request"], state["decision"])
    response.research_steps = complete_planning_steps(plan)
    return _final_state(
        {**state, "events": [*state.get("events", []), {"event": "research_plan", "data": plan}]},
        response,
    )


def _run_search(agent: Any, state: ChatbotGraphState) -> ChatbotGraphState:
    events = list(agent.search_node.stream(state["request"], state["decision"]))
    response = _final_response_from_events(events)
    return {
        "response": response,
        "events": [*state.get("events", []), *events],
    }


def _run_research(agent: Any, state: ChatbotGraphState) -> ChatbotGraphState:
    events = list(agent.research_node.stream(state["request"], state["decision"]))
    response = _final_response_from_events(events)
    return {
        "response": response,
        "events": [*state.get("events", []), *events],
    }


def _final_state(
    state: ChatbotGraphState,
    response: ChatbotMessageResponse,
) -> ChatbotGraphState:
    return {
        "response": response,
        "events": [
            *state.get("events", []),
            {"event": "final", "data": response},
        ],
    }


def _final_response_from_events(events: list[dict[str, Any]]) -> ChatbotMessageResponse:
    for event in reversed(events):
        if event.get("event") == "final":
            response = event.get("data")
            if isinstance(response, ChatbotMessageResponse):
                return response
    raise RuntimeError("Chatbot graph node finished without a final response.")


def stream_graph_events(compiled_graph: Any, request: ChatbotMessageRequest) -> Iterator[dict[str, Any]]:
    result = compiled_graph.invoke({"request": request, "events": []})
    yield from result.get("events", [])


def stream_chatbot_graph(agent: Any, request: ChatbotMessageRequest) -> Iterator[dict[str, Any]]:
    classify_graph = StateGraph(ChatbotGraphState)
    classify_graph.add_node("classify_intent", lambda state: _classify_intent(agent, state))
    classify_graph.set_entry_point("classify_intent")
    classify_graph.add_edge("classify_intent", END)
    state = classify_graph.compile().invoke({"request": request, "events": []})
    yield from state.get("events", [])

    decision = state["decision"]
    route = _route_from_decision(state)
    if route == "search":
        yield from agent.search_node.stream(request, decision)
        return
    if route == "research":
        yield from agent.research_node.stream(request, decision)
        return
    if route == "update":
        plan = build_planning_steps(request, decision)
        yield {"event": "research_plan", "data": plan}
        response = agent.update_node.run(request, decision)
        response.research_steps = complete_planning_steps(plan)
    else:
        plan = build_planning_steps(request, decision)
        yield {"event": "research_plan", "data": plan}
        response = agent.ask_node.run(request, decision)
        response.research_steps = complete_planning_steps(plan)
    yield {"event": "final", "data": response}
