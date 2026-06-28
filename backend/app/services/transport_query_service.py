from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
import re
from typing import Any

from app import config
from app.integrations.mcp_12306 import Mcp12306Error, Remote12306McpClient


TRAIN_TICKET_QUERY_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "date",
        "from_station",
        "to_station",
        "train_filter_flags",
        "earliest_start_time",
        "latest_start_time",
        "direct_only",
        "seat_preference",
    ],
    "properties": {
        "date": {
            "type": "string",
            "description": "出行日期，格式 YYYY-MM-DD；相对日期必须基于 current_date 计算。",
            "pattern": "^20\\d{2}-\\d{2}-\\d{2}$",
        },
        "from_station": {
            "type": "string",
            "description": "中文出发城市或车站名，去掉“从/查询/帮我查”等前缀。",
            "minLength": 1,
        },
        "to_station": {
            "type": "string",
            "description": "中文到达城市或车站名。",
            "minLength": 1,
        },
        "train_filter_flags": {
            "type": "string",
            "description": "车次类型过滤；高铁/G字头为 G，动车/D字头为 D；不确定时默认 G。",
            "enum": ["G", "D"],
        },
        "earliest_start_time": {
            "type": "integer",
            "description": "最早出发小时，0 到 24 的整数。",
            "minimum": 0,
            "maximum": 24,
        },
        "latest_start_time": {
            "type": "integer",
            "description": "最晚出发小时，0 到 24 的整数，必须大于 earliest_start_time。",
            "minimum": 0,
            "maximum": 24,
        },
        "direct_only": {
            "type": "boolean",
            "description": "用户说直达、不中转、不接受中转、不要中转时为 true；明确接受中转时为 false。",
        },
        "seat_preference": {
            "type": "string",
            "description": "用户指定席别原文，例如 商务座、一等座、二等座；没有则为空字符串。",
        },
    },
}


def _build_train_ticket_query_parser_system_prompt(
    output_schema_: dict[str, Any] = TRAIN_TICKET_QUERY_OUTPUT_SCHEMA,
) -> str:
    return (
        "你是中国铁路 12306 查询参数解析器。\n\n"
        "任务：把用户的自然语言铁路查询转换为 12306 MCP get-tickets 可用参数。\n\n"
        "只返回一个符合 schema 的 JSON 对象，不要 Markdown，不要解释，不要追加文字。\n\n"
        "<OUTPUT JSON SCHEMA>\n"
        f"{json.dumps(output_schema_, indent=2, ensure_ascii=False)}\n"
        "</OUTPUT JSON SCHEMA>\n\n"
        "时间窗规则：\n"
        "- 上午/早上/早晨 => 6 到 12\n"
        "- 中午 => 11 到 14\n"
        "- 下午 => 12 到 18\n"
        "- 晚上/夜里 => 18 到 24\n"
        "- 明确小时范围按用户给出的范围解析，并把小时限制在 0 到 24。\n\n"
        "如果缺少路线、日期或时间窗，也必须尽力基于原文和 current_date 返回 JSON，不要提问。"
    )


TRAIN_TICKET_QUERY_PARSER_SYSTEM_PROMPT = _build_train_ticket_query_parser_system_prompt()


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
    seat_preference: str = ""
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
    llm: Any | None = None,
    client: Remote12306McpClient | None = None,
) -> TrainTicketQueryResult:
    if not config.ENABLE_12306_MCP:
        raise TransportQueryUnavailable("12306 MCP 未启用。")
    query = parse_train_ticket_query(
        f"{message} {search_query}".strip(),
        max_results=config.MCP_12306_MAX_RESULTS,
        llm=llm,
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


def parse_train_ticket_query(
    message: str,
    *,
    max_results: int = 20,
    llm: Any | None = None,
) -> TrainTicketQuery:
    if llm is not None:
        llm_query = _parse_train_ticket_query_with_llm(
            message,
            max_results=max_results,
            llm=llm,
        )
        if llm_query is not None:
            return llm_query
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
        seat_preference=_extract_seat_preference(message),
        max_results=max_results,
    )


def _parse_train_ticket_query_with_llm(
    message: str,
    *,
    max_results: int,
    llm: Any,
) -> TrainTicketQuery | None:
    try:
        response = llm.invoke(
            [
                ("system", TRAIN_TICKET_QUERY_PARSER_SYSTEM_PROMPT),
                (
                    "human",
                    json.dumps(
                        {
                            "current_date": date.today().isoformat(),
                            "message": message,
                        },
                        ensure_ascii=False,
                    ),
                ),
            ]
        )
        raw_text = _response_content_to_text(response)
        json_text = _extract_json_object(raw_text)
        if json_text is None:
            return None
        payload = json.loads(json_text)
        if not isinstance(payload, dict):
            return None
        return _train_ticket_query_from_llm_payload(payload, max_results=max_results)
    except Exception:
        return None


def _train_ticket_query_from_llm_payload(
    payload: dict[str, Any],
    *,
    max_results: int,
) -> TrainTicketQuery | None:
    try:
        parsed_date = datetime.strptime(str(payload.get("date") or ""), "%Y-%m-%d").date()
        from_station = _clean_station(str(payload.get("from_station") or ""))
        to_station = _clean_station(str(payload.get("to_station") or ""))
        if not from_station or not to_station:
            return None
        earliest = _clamp_hour(int(payload.get("earliest_start_time")))
        latest = _clamp_hour(int(payload.get("latest_start_time")))
        if latest <= earliest:
            latest = _clamp_hour(earliest + 1)
        train_filter_flags = str(payload.get("train_filter_flags") or "G").upper()
        if train_filter_flags not in {"G", "D"}:
            train_filter_flags = "G"
        return TrainTicketQuery(
            date=parsed_date.isoformat(),
            from_station=from_station,
            to_station=to_station,
            train_filter_flags=train_filter_flags,
            earliest_start_time=earliest,
            latest_start_time=latest,
            direct_only=_to_bool(payload.get("direct_only", True)),
            seat_preference=str(payload.get("seat_preference") or "").strip(),
            max_results=max_results,
        )
    except (TypeError, ValueError):
        return None


def format_train_ticket_answer(result: TrainTicketQueryResult) -> str:
    lines = [
        "## 明确结论",
        (
            f"已查到 {result.query.date} {result.query.earliest_start_time:02d}:00-"
            f"{result.query.latest_start_time:02d}:00 从{result.query.from_station}到"
            f"{result.query.to_station}的直达铁路余票。以下为 12306 MCP 返回的实时结果摘要。"
        ),
        "",
    ]
    if result.query.seat_preference:
        lines.extend([f"席别偏好：{result.query.seat_preference}", ""])
    lines.append("## 推荐直达车次")
    for ticket in result.tickets:
        seats = _sort_preferred_seats(ticket.seats, result.query.seat_preference)
        seat_text = "；".join(_format_seat(seat) for seat in seats[:4]) or "席别未返回"
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


def _response_content_to_text(response: object) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _extract_json_object(raw_text: str) -> str | None:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    start_index = text.find("{")
    end_index = text.rfind("}")
    if start_index == -1 or end_index == -1 or end_index <= start_index:
        return None
    return text[start_index : end_index + 1]


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


def _extract_seat_preference(message: str) -> str:
    for seat_name in ("商务座", "特等座", "一等座", "二等座", "软卧", "硬卧", "软座", "硬座", "无座"):
        if seat_name in message:
            return seat_name
    return ""


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


def _sort_preferred_seats(seats: list[TrainSeat], seat_preference: str) -> list[TrainSeat]:
    if not seat_preference:
        return seats
    return sorted(seats, key=lambda seat: 0 if seat.seat_name == seat_preference else 1)


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


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "no", "否", "不", "不接受"}:
            return False
        if normalized in {"true", "1", "yes", "是", "接受"}:
            return True
    return bool(value)
