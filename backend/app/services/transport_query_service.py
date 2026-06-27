from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import re
from typing import Any

from app import config
from app.integrations.mcp_12306 import Mcp12306Error, Remote12306McpClient


@dataclass(frozen=True)
class TrainSeat:
    seat_name: str
    availability: str
    price: float | None


@dataclass(frozen=True)
class TrainTicket:
    train_code: str
    from_station: str
    to_station: str
    start_time: str
    arrive_time: str
    duration: str
    date: str
    seats: list[TrainSeat] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TrainTicketQuery:
    date: str
    from_station: str
    to_station: str
    train_filter_flags: str = "G"
    earliest_start_time: int = 6
    latest_start_time: int = 12
    direct_only: bool = True
    max_results: int = 20


@dataclass(frozen=True)
class TrainTicketQueryResult:
    query: TrainTicketQuery
    tickets: list[TrainTicket]
    source_title: str = "中国铁路12306 / 12306 MCP"
    source_url: str = "https://www.12306.cn/index/"


class TransportQueryUnavailable(RuntimeError):
    """Raised when realtime transport data should fall back to web search."""


def query_realtime_train_tickets(
    message: str,
    *,
    search_query: str = "",
    client: Remote12306McpClient | None = None,
) -> TrainTicketQueryResult:
    if not config.ENABLE_12306_MCP:
        raise TransportQueryUnavailable("12306 MCP 未启用。")
    query = parse_train_ticket_query(
        f"{message} {search_query}".strip(),
        max_results=config.MCP_12306_MAX_RESULTS,
    )
    resolved_client = client or Remote12306McpClient(
        url=config.MCP_12306_URL,
        timeout_seconds=config.MCP_12306_TIMEOUT_SECONDS,
    )
    try:
        result = resolved_client.call_tool(
            "get-tickets",
            {
                "date": query.date,
                "fromStation": query.from_station,
                "toStation": query.to_station,
                "trainFilterFlags": query.train_filter_flags,
                "earliestStartTime": query.earliest_start_time,
                "latestStartTime": query.latest_start_time,
                "sortFlag": "startTime",
                "sortReverse": False,
                "limitedNum": query.max_results,
                "format": "json",
            },
        )
    except Mcp12306Error as exc:
        raise TransportQueryUnavailable(str(exc)) from exc
    if not isinstance(result.payload, list):
        raise TransportQueryUnavailable("12306 MCP 未返回可解析的车次列表。")
    tickets = [_normalize_ticket(item) for item in result.payload if isinstance(item, dict)]
    if not tickets:
        raise TransportQueryUnavailable("12306 MCP 没有返回匹配的直达车次。")
    return TrainTicketQueryResult(query=query, tickets=tickets)


def parse_train_ticket_query(message: str, *, max_results: int = 20) -> TrainTicketQuery:
    target_date = _extract_date(message)
    earliest, latest = _extract_time_window(message)
    from_station, to_station = _extract_route(message)
    return TrainTicketQuery(
        date=target_date.isoformat(),
        from_station=from_station,
        to_station=to_station,
        train_filter_flags=_extract_train_filter_flags(message),
        earliest_start_time=earliest,
        latest_start_time=latest,
        direct_only=_is_direct_only(message),
        max_results=max_results,
    )


def format_train_ticket_answer(result: TrainTicketQueryResult) -> str:
    lines = [
        "## 明确结论",
        (
            f"已查到 {result.query.date} {result.query.earliest_start_time:02d}:00-"
            f"{result.query.latest_start_time:02d}:00 从{result.query.from_station}到"
            f"{result.query.to_station}的直达铁路余票。以下为 12306 MCP 返回的实时结果摘要。"
        ),
        "",
        "## 推荐直达车次",
    ]
    for ticket in result.tickets:
        seat_text = "；".join(_format_seat(seat) for seat in ticket.seats[:4]) or "席别未返回"
        flags = f"（{'、'.join(ticket.flags)}）" if ticket.flags else ""
        lines.append(
            f"- {ticket.train_code} {ticket.from_station} {ticket.start_time} -> "
            f"{ticket.to_station} {ticket.arrive_time}，历时 {ticket.duration}{flags}；{seat_text}"
        )
    lines.extend(
        [
            "",
            "## 来源与注意",
            f"- 来源：[{result.source_title}]({result.source_url})",
            "- 余票、票价和可购买状态变化很快，最终购票、锁票和候补以 12306 官方页面为准。",
        ]
    )
    return "\n".join(lines)


def train_ticket_source_content(result: TrainTicketQueryResult) -> str:
    return (
        f"{result.query.date} {result.query.from_station}到{result.query.to_station}"
        f"返回 {len(result.tickets)} 条直达车次。"
    )


def _extract_date(message: str) -> date:
    match = re.search(r"20\d{2}-\d{1,2}-\d{1,2}", message)
    if match:
        return datetime.strptime(match.group(0), "%Y-%m-%d").date()
    today = date.today()
    if "后天" in message:
        return today + timedelta(days=2)
    if "明天" in message or "明日" in message:
        return today + timedelta(days=1)
    return today


def _extract_time_window(message: str) -> tuple[int, int]:
    time_text = re.sub(r"20\d{2}-\d{1,2}-\d{1,2}", "", message)
    range_match = re.search(r"(\d{1,2})(?::\d{2})?\s*[-到至~]\s*(\d{1,2})(?::\d{2})?", time_text)
    if range_match:
        start = _clamp_hour(int(range_match.group(1)))
        end = _clamp_hour(int(range_match.group(2)))
        return (start, _clamp_hour(max(start + 1, end)))
    if "上午" in message or "早上" in message or "早晨" in message:
        return (6, 12)
    if "中午" in message:
        return (11, 14)
    if "下午" in message:
        return (12, 18)
    if "晚上" in message or "夜里" in message:
        return (18, 24)
    return (0, 24)


def _extract_route(message: str) -> tuple[str, str]:
    patterns = [
        r"从([\u4e00-\u9fff]{2,10}?)(?:出发)?(?:到|去|至)([\u4e00-\u9fff]{2,10}?)(?=的|高铁|动车|火车|车票|票|明天|今天|后天|上午|下午|晚上|[\s,，。]|$)",
        r"([\u4e00-\u9fff]{2,10}?)(?:到|去|至)([\u4e00-\u9fff]{2,10}?)(?=的|高铁|动车|火车|车票|票|明天|今天|后天|上午|下午|晚上|[\s,，。]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return (_clean_station(match.group(1)), _clean_station(match.group(2)))
    raise TransportQueryUnavailable("未能识别铁路查询的出发地和到达地。")


def _extract_train_filter_flags(message: str) -> str:
    if "高铁" in message or re.search(r"\bG\b|G字头", message, flags=re.IGNORECASE):
        return "G"
    if "动车" in message or re.search(r"\bD\b|D字头", message, flags=re.IGNORECASE):
        return "D"
    return "G"


def _is_direct_only(message: str) -> bool:
    return any(word in message for word in ("直达", "不中转", "不接受中转", "不要中转"))


def _normalize_ticket(item: dict[str, Any]) -> TrainTicket:
    seats = []
    for price in item.get("prices") or []:
        if isinstance(price, dict):
            seats.append(
                TrainSeat(
                    seat_name=str(price.get("seat_name") or "席别未返回"),
                    availability=str(price.get("num") or "未返回"),
                    price=_to_float_or_none(price.get("price")),
                )
            )
    return TrainTicket(
        train_code=str(item.get("start_train_code") or "车次未返回"),
        from_station=str(item.get("from_station") or "出发站未返回"),
        to_station=str(item.get("to_station") or "到达站未返回"),
        start_time=str(item.get("start_time") or "未返回"),
        arrive_time=str(item.get("arrive_time") or "未返回"),
        duration=str(item.get("lishi") or "未返回"),
        date=str(item.get("start_date") or "日期未返回"),
        seats=seats,
        flags=[str(flag) for flag in (item.get("dw_flag") or []) if flag],
    )


def _format_seat(seat: TrainSeat) -> str:
    price = "价格未返回" if seat.price is None else f"{seat.price:g}元"
    return f"{seat.seat_name}{seat.availability}，{price}"


def _clean_station(value: str) -> str:
    return re.sub(r"^(从|查|查询|帮我查|我想查)", "", value).strip(" ，,。")


def _clamp_hour(hour: int) -> int:
    return max(0, min(24, hour))


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
