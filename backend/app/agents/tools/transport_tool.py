from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.transport_query_service import (
    TrainTicket,
    TransportQueryUnavailable,
    format_train_ticket_answer,
    query_realtime_train_tickets,
)


@dataclass(frozen=True)
class TransportToolResult:
    available: bool
    answer: str
    source_notes: list[str]
    tickets: list[TrainTicket]
    error_message: str = ""


def search_train_tickets_for_agent(
    message: str,
    search_query: str = "",
    llm: Any | None = None,
) -> TransportToolResult:
    try:
        result = query_realtime_train_tickets(
            message,
            search_query=search_query,
            llm=llm if llm is not None else _build_llm_or_none(),
        )
    except TransportQueryUnavailable as exc:
        return TransportToolResult(
            available=False,
            answer="",
            source_notes=[],
            tickets=[],
            error_message=str(exc),
        )
    except Exception as exc:
        return TransportToolResult(
            available=False,
            answer="",
            source_notes=[],
            tickets=[],
            error_message=f"12306 MCP 查询失败：{exc}",
        )

    return TransportToolResult(
        available=True,
        answer=format_train_ticket_answer(result),
        source_notes=[
            f"来源：{result.source_title} {result.source_url}",
            "余票、票价和可购买状态变化很快，最终购票、锁票和候补以 12306 官方页面为准。",
        ],
        tickets=result.tickets,
    )


def _build_llm_or_none() -> Any | None:
    try:
        from app.agents.trip_planner_agent.llms import build_chat_llm

        return build_chat_llm()
    except Exception:
        return None
