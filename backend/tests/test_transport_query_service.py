from __future__ import annotations

import pytest

from app.integrations.mcp_12306 import Mcp12306Error, parse_mcp_http_response
from app.services import transport_query_service as service
from app.agents.tools import transport_tool
from app.services.transport_query_service import (
    TransportQueryUnavailable,
    format_train_ticket_answer,
    parse_train_ticket_query,
    query_realtime_train_tickets,
)


def test_parse_mcp_http_response_extracts_sse_json() -> None:
    payload = parse_mcp_http_response(
        'event: message\n'
        'data: {"result":{"content":[{"type":"text","text":"[]"}]},"jsonrpc":"2.0","id":1}\n'
    )

    assert payload["result"]["content"][0]["text"] == "[]"


def test_parse_mcp_http_response_raises_jsonrpc_error() -> None:
    with pytest.raises(Mcp12306Error, match="Method not allowed"):
        parse_mcp_http_response(
            'event: message\n'
            'data: {"jsonrpc":"2.0","error":{"code":-32000,"message":"Method not allowed"},"id":1}\n'
        )


def test_parse_train_ticket_query_extracts_tomorrow_morning_direct_high_speed(
    monkeypatch,
) -> None:
    class FixedDate(service.date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 27)

    monkeypatch.setattr(service, "date", FixedDate)

    query = parse_train_ticket_query("高铁，上海到杭州，明天上午，接受直达优先，不中转", max_results=20)

    assert query.date == "2026-06-28"
    assert query.from_station == "上海"
    assert query.to_station == "杭州"
    assert query.train_filter_flags == "G"
    assert query.earliest_start_time == 6
    assert query.latest_start_time == 12
    assert query.direct_only is True
    assert query.max_results == 20


def test_parse_train_ticket_query_does_not_treat_iso_date_as_time_range() -> None:
    query = parse_train_ticket_query("上海到杭州 2026-06-28 上午 高铁 直达")

    assert query.date == "2026-06-28"
    assert query.earliest_start_time == 6
    assert query.latest_start_time == 12


def test_query_realtime_train_tickets_prefers_llm_json_params(monkeypatch) -> None:
    monkeypatch.setattr(service.config, "ENABLE_12306_MCP", True)
    monkeypatch.setattr(service.config, "MCP_12306_MAX_RESULTS", 20)

    class FixedDate(service.date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 27)

    monkeypatch.setattr(service, "date", FixedDate)
    calls = []

    class FakeResponse:
        content = """
        ```json
        {
          "date": "2026-06-28",
          "from_station": "北京",
          "to_station": "杭州",
          "train_filter_flags": "G",
          "earliest_start_time": 6,
          "latest_start_time": 12,
          "direct_only": true,
          "seat_preference": "商务座"
        }
        ```
        """

    class FakeLLM:
        def __init__(self):
            self.messages = None

        def invoke(self, messages):
            self.messages = messages
            return FakeResponse()

    class FakeClient:
        def call_tool(self, name, arguments):
            calls.append((name, arguments))

            class Result:
                payload = [
                    {
                        "start_train_code": "G31",
                        "from_station": "北京南",
                        "to_station": "杭州东",
                        "start_time": "08:12",
                        "arrive_time": "13:00",
                        "lishi": "04:48",
                        "start_date": "2026-06-28",
                        "prices": [
                            {"seat_name": "商务座", "num": "有", "price": 1847},
                            {"seat_name": "二等座", "num": "有", "price": 538.5},
                        ],
                    }
                ]

            return Result()

    llm = FakeLLM()
    result = query_realtime_train_tickets(
        "高铁，北京到杭州，明天上午，接受直达优先，不中转，商务座",
        client=FakeClient(),
        llm=llm,
    )

    assert calls == [
        (
            "get-tickets",
            {
                "date": "2026-06-28",
                "fromStation": "北京",
                "toStation": "杭州",
                "trainFilterFlags": "G",
                "earliestStartTime": 6,
                "latestStartTime": 12,
                "sortFlag": "startTime",
                "sortReverse": False,
                "limitedNum": 20,
                "format": "json",
            },
        )
    ]
    assert result.query.seat_preference == "商务座"
    assert "商务座有，1847元" in format_train_ticket_answer(result)
    assert llm.messages is not None
    assert llm.messages[0][0] == "system"
    assert "<OUTPUT JSON SCHEMA>" in llm.messages[0][1]
    assert "</OUTPUT JSON SCHEMA>" in llm.messages[0][1]
    assert '"required": [' in llm.messages[0][1]
    assert '"seat_preference"' in llm.messages[0][1]
    assert '"additionalProperties": false' in llm.messages[0][1]
    assert "2026-06-27" in llm.messages[1][1]
    assert "商务座" in llm.messages[1][1]


def test_parse_train_ticket_query_falls_back_when_llm_json_is_invalid(monkeypatch) -> None:
    class FixedDate(service.date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 27)

    monkeypatch.setattr(service, "date", FixedDate)

    class FakeResponse:
        content = "我需要更多信息"

    class FakeLLM:
        def invoke(self, messages):
            return FakeResponse()

    query = parse_train_ticket_query(
        "高铁，上海到杭州，明天上午，接受直达优先，不中转",
        max_results=20,
        llm=FakeLLM(),
    )

    assert query.date == "2026-06-28"
    assert query.from_station == "上海"
    assert query.to_station == "杭州"
    assert query.train_filter_flags == "G"
    assert query.earliest_start_time == 6
    assert query.latest_start_time == 12
    assert query.direct_only is True


def test_format_train_ticket_answer_surfaces_preferred_seat_first() -> None:
    result = service.TrainTicketQueryResult(
        query=service.TrainTicketQuery(
            date="2026-06-28",
            from_station="北京",
            to_station="杭州",
            seat_preference="商务座",
        ),
        tickets=[
            service.TrainTicket(
                train_code="G31",
                from_station="北京南",
                to_station="杭州东",
                start_time="08:12",
                arrive_time="13:00",
                duration="04:48",
                date="2026-06-28",
                seats=[
                    service.TrainSeat("二等座", "有", 538.5),
                    service.TrainSeat("商务座", "有", 1847),
                    service.TrainSeat("一等座", "有", 907),
                ],
            )
        ],
    )

    answer = format_train_ticket_answer(result)

    assert "席别偏好：商务座" in answer
    assert "商务座有，1847元；二等座有，538.5元" in answer


def test_query_realtime_train_tickets_calls_get_tickets_and_formats_answer(monkeypatch) -> None:
    monkeypatch.setattr(service.config, "ENABLE_12306_MCP", True)
    monkeypatch.setattr(service.config, "MCP_12306_MAX_RESULTS", 20)

    class FixedDate(service.date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 27)

    monkeypatch.setattr(service, "date", FixedDate)
    calls = []

    class FakeClient:
        def call_tool(self, name, arguments):
            calls.append((name, arguments))

            class Result:
                payload = [
                    {
                        "start_train_code": "G205",
                        "from_station": "上海虹桥",
                        "to_station": "杭州东",
                        "start_time": "07:00",
                        "arrive_time": "07:45",
                        "lishi": "00:45",
                        "start_date": "2026-06-28",
                        "prices": [
                            {"seat_name": "二等座", "num": "有", "price": 87},
                            {"seat_name": "一等座", "num": "有", "price": 140},
                        ],
                        "dw_flag": ["复兴号"],
                    }
                ]

            return Result()

    result = query_realtime_train_tickets(
        "上海到杭州 明天上午 高铁 直达 不接受中转",
        client=FakeClient(),
    )

    assert calls == [
        (
            "get-tickets",
            {
                "date": "2026-06-28",
                "fromStation": "上海",
                "toStation": "杭州",
                "trainFilterFlags": "G",
                "earliestStartTime": 6,
                "latestStartTime": 12,
                "sortFlag": "startTime",
                "sortReverse": False,
                "limitedNum": 20,
                "format": "json",
            },
        )
    ]
    answer = format_train_ticket_answer(result)
    assert "G205" in answer
    assert "上海虹桥 07:00 -> 杭州东 07:45" in answer
    assert "二等座有，87元" in answer
    assert "12306 官方页面为准" in answer


def test_query_realtime_train_tickets_disabled_raises_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(service.config, "ENABLE_12306_MCP", False)

    with pytest.raises(TransportQueryUnavailable, match="未启用"):
        query_realtime_train_tickets("上海到杭州 明天上午 高铁")


def test_transport_tool_returns_available_result(monkeypatch) -> None:
    monkeypatch.setattr(service.config, "ENABLE_12306_MCP", True)
    monkeypatch.setattr(service.config, "MCP_12306_MAX_RESULTS", 20)

    class FixedDate(service.date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 27)

    monkeypatch.setattr(service, "date", FixedDate)
    calls = []

    class FakeClient:
        def call_tool(self, name, arguments):
            calls.append((name, arguments))

            class Result:
                payload = [
                    {
                        "start_train_code": "G205",
                        "from_station": "上海虹桥",
                        "to_station": "杭州东",
                        "start_time": "07:00",
                        "arrive_time": "07:45",
                        "lishi": "00:45",
                        "start_date": "2026-06-28",
                        "prices": [{"seat_name": "二等座", "num": "有", "price": 87}],
                    }
                ]

            return Result()

    monkeypatch.setattr(
        service,
        "Remote12306McpClient",
        lambda *, url, timeout_seconds: FakeClient(),
    )

    result = transport_tool.search_train_tickets_for_agent(
        "上海到杭州 明天上午 高铁 直达"
    )

    assert result.available is True
    assert result.error_message == ""
    assert result.tickets[0].train_code == "G205"
    assert "G205" in result.answer
    assert result.source_notes == [
        "来源：中国铁路12306 / 12306 MCP https://www.12306.cn/index/",
        "余票、票价和可购买状态变化很快，最终购票、锁票和候补以 12306 官方页面为准。",
    ]
    assert [name for name, _arguments in calls] == ["get-tickets"]


def test_transport_tool_lazily_builds_llm_when_not_provided(monkeypatch) -> None:
    monkeypatch.setattr(service.config, "ENABLE_12306_MCP", True)
    monkeypatch.setattr(service.config, "MCP_12306_MAX_RESULTS", 20)

    class FixedDate(service.date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 27)

    monkeypatch.setattr(service, "date", FixedDate)

    class FakeResponse:
        content = (
            '{"date":"2026-06-28","from_station":"北京","to_station":"杭州",'
            '"train_filter_flags":"G","earliest_start_time":6,"latest_start_time":12,'
            '"direct_only":true,"seat_preference":"商务座"}'
        )

    class FakeLLM:
        def __init__(self):
            self.invoked = False

        def invoke(self, messages):
            self.invoked = True
            return FakeResponse()

    fake_llm = FakeLLM()
    monkeypatch.setattr(transport_tool, "_build_llm_or_none", lambda: fake_llm)
    calls = []

    class FakeClient:
        def call_tool(self, name, arguments):
            calls.append((name, arguments))

            class Result:
                payload = [
                    {
                        "start_train_code": "G31",
                        "from_station": "北京南",
                        "to_station": "杭州东",
                        "start_time": "08:12",
                        "arrive_time": "13:00",
                        "lishi": "04:48",
                        "start_date": "2026-06-28",
                        "prices": [{"seat_name": "商务座", "num": "有", "price": 1847}],
                    }
                ]

            return Result()

    monkeypatch.setattr(
        service,
        "Remote12306McpClient",
        lambda *, url, timeout_seconds: FakeClient(),
    )

    result = transport_tool.search_train_tickets_for_agent(
        "高铁，北京到杭州，明天上午，接受直达优先，不中转，商务座"
    )

    assert result.available is True
    assert fake_llm.invoked is True
    assert calls[0][1]["fromStation"] == "北京"
    assert "席别偏好：商务座" in result.answer


def test_transport_tool_returns_unavailable_without_raising(monkeypatch) -> None:
    monkeypatch.setattr(service.config, "ENABLE_12306_MCP", False)

    result = transport_tool.search_train_tickets_for_agent("上海到杭州 明天上午 高铁")

    assert result.available is False
    assert result.answer == ""
    assert result.tickets == []
    assert "未启用" in result.error_message
