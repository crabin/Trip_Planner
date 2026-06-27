from __future__ import annotations

from datetime import date
import json
import time

from fastapi.testclient import TestClient

from app.agents.chatbot_agent import agent as chatbot_agent
from app.agents.chatbot_agent.agent import ChatbotAgent
from app.agents.chatbot_agent.prompts.intent import INTENT_CLASSIFIER_SYSTEM_PROMPT
from app.agents.chatbot_agent.prompts.realtime import REALTIME_QUERY_ROUTER_SYSTEM_PROMPT
from app.agents.chatbot_agent.state import IntentDecision
from app.agents.chatbot_agent.utils import build_research_steps
from app.api.main import app
from app.models.schemas import (
    BudgetBreakdown,
    ChatbotMessageRequest,
    DayPlan,
    Itinerary,
    MealItem,
    SpotItem,
)
from app.agents.tools.transport_tool import TransportToolResult
from app.integrations.web_search import SearchResult, TavilyResponse
from app.services.transport_query_service import TrainTicket


def test_json_output_prompts_use_output_schema_blocks() -> None:
    for prompt in (INTENT_CLASSIFIER_SYSTEM_PROMPT, REALTIME_QUERY_ROUTER_SYSTEM_PROMPT):
        assert "<OUTPUT JSON SCHEMA>" in prompt
        assert "</OUTPUT JSON SCHEMA>" in prompt
        assert '"type": "object"' in prompt
        assert '"additionalProperties": false' in prompt

    assert '"intent"' in INTENT_CLASSIFIER_SYSTEM_PROMPT
    assert '"query_kind"' in REALTIME_QUERY_ROUTER_SYSTEM_PROMPT


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatLLM:
    def __init__(
        self,
        *,
        intent: str,
        route_kind: str = "generic_search",
        route_query: str | None = None,
        edit_scope: str | None = None,
        search_queries: list[str] | None = None,
        generation_tasks: list[str] | None = None,
        answer_strategy: str | None = None,
        summary: str | None = None,
    ) -> None:
        self.intent = intent
        self.route_kind = route_kind
        self.route_query = route_query
        self.edit_scope = edit_scope
        self.search_queries = search_queries or []
        self.generation_tasks = generation_tasks or []
        self.answer_strategy = answer_strategy
        self.summary = summary
        self.intent_invocations = 0
        self.intent_payload = {}
        self.ask_payload = {}
        self.summary_payload = {}
        self.realtime_summary_payload = {}

    def invoke(self, messages):
        system = messages[0][1]
        if "实时查询路由器" in system:
            return FakeResponse(
                (
                    '{"query_kind":"%s","search_query":"%s","reason":"测试路由"}'
                    % (self.route_kind, self.route_query or "")
                )
            )
        if "实时网页搜索证据" in system:
            self.realtime_summary_payload = json.loads(messages[1][1])
            if self.summary:
                return FakeResponse(self.summary)
            source = (self.realtime_summary_payload.get("sources") or [{}])[0]
            source_title = source.get("title") or "测试来源"
            source_url = source.get("url") or "https://example.com"
            if not self.realtime_summary_payload.get("reliability", {}).get("has_reliable_source"):
                return FakeResponse(
                    "## 当前线索\n"
                    f"{source_title} 提供了可参考线索，但暂时不足以确认实时状态。\n\n"
                    "## 来源\n"
                    f"- [{source_title}]({source_url})"
                )
            return FakeResponse(
                "## 明确结论\n"
                f"{source_title} 显示有可参考信息，但涉及实时状态仍需以官方渠道复核。\n\n"
                "## 来源\n"
                f"- [{source_title}]({source_url})"
            )
        if "意图分类器" in system:
            self.intent_invocations += 1
            self.intent_payload = json.loads(messages[1][1])
            queries = ",".join(f'"{query}"' for query in self.search_queries)
            tasks = ",".join(f'"{task}"' for task in self.generation_tasks)
            edit_scope = f'"{self.edit_scope}"' if self.edit_scope else "null"
            return FakeResponse(
                (
                    '{"intent":"%s","reason":"测试意图","answer_strategy":"%s",'
                    '"search_query":"%s","edit_scope":%s,'
                    '"search_queries":[%s],"generation_tasks":[%s]}'
                )
                % (
                    self.intent,
                    self.answer_strategy or "先分析需求，再执行查询和生成计划，最后回答。",
                    self.route_query or "",
                    edit_scope,
                    queries,
                    tasks,
                )
            )
        if "普通问答生成器" in system:
            self.ask_payload = json.loads(messages[1][1])
            message = self.ask_payload["message"]
            if "你是谁" in message:
                return FakeResponse("我是智旅顾问，可以帮你规划、调整、查询和比较旅行方案。")
            if "查找内容" in message or "搜索" in message:
                return FakeResponse(
                    "可以。你给我目的地、日期或具体对象后，我可以查询景点开放、门票预约、天气、交通、住宿区域和旅行风险等信息。"
                )
            return FakeResponse(f"这是围绕“{message}”生成的回答。")
        if "智旅顾问" in system or "专业旅行顾问" in system:
            self.summary_payload = json.loads(messages[1][1])
        if self.summary:
            return FakeResponse(self.summary)
        raise AssertionError(f"Unexpected LLM prompt: {system}")


def build_itinerary() -> Itinerary:
    return Itinerary(
        trip_id="trip_test",
        destination="成都",
        summary="成都三日轻松游",
        days=[
            DayPlan(
                day_index=1,
                theme="市区慢游",
                spots=[SpotItem(name="宽窄巷子", description="慢慢逛。")],
                meals=[MealItem(name="川菜馆", meal_type="午餐")],
                notes=["别太早起"],
            ),
            DayPlan(
                day_index=2,
                theme="熊猫基地",
                spots=[SpotItem(name="大熊猫繁育研究基地", description="上午游览。")],
                meals=[MealItem(name="茶馆", meal_type="下午茶")],
                notes=["预留打车时间"],
            ),
        ],
        estimated_budget=3200,
        budget_breakdown=BudgetBreakdown(total=3200),
        tips=["出发前确认天气"],
        source_notes=[],
    )


def test_chatbot_agent_answers_with_current_itinerary(monkeypatch) -> None:
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: None)
    request = ChatbotMessageRequest(
        message="这个行程预算多少？",
        current_itinerary=build_itinerary(),
    )

    response = ChatbotAgent().handle(request)

    assert response.intent == "ask"
    assert "成都" in response.reply
    assert "3200" in response.reply
    assert response.updated_itinerary is None


def test_chatbot_agent_uses_llm_for_identity_question(monkeypatch) -> None:
    fake_llm = FakeChatLLM(intent="ask")
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)

    response = ChatbotAgent().handle(ChatbotMessageRequest(message="你是谁"))

    assert response.intent == "ask"
    assert response.reply == "我是智旅顾问，可以帮你规划、调整、查询和比较旅行方案。"
    assert fake_llm.ask_payload["message"] == "你是谁"
    assert "目的地、日期、人数、预算和节奏" not in response.reply
    assert "调研完成" not in response.reply


def test_chatbot_agent_uses_llm_for_search_capability_question(monkeypatch) -> None:
    fake_llm = FakeChatLLM(intent="ask")
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)

    response = ChatbotAgent().handle(ChatbotMessageRequest(message="你能不能查找内容"))

    assert response.intent == "ask"
    assert "可以" in response.reply
    assert "景点开放" in response.reply
    assert fake_llm.ask_payload["message"] == "你能不能查找内容"
    assert response.reply != "我是你的智旅顾问，会先帮你理清目的地、日期、人数、预算和节奏，再给可执行建议。你可以先告诉我这次旅行最重要的约束。"
    assert "提示词" not in response.reply


def test_chatbot_agent_updates_current_itinerary(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(intent="update", edit_scope="day_2"),
    )
    original = build_itinerary()
    updated = original.model_copy(deep=True)
    updated.days[1].theme = "更轻松的第二天"

    captured = {}

    def fake_edit_trip_itinerary(request):
        captured["edit_scope"] = request.edit_scope
        captured["instruction"] = request.user_instruction
        return updated

    monkeypatch.setattr(chatbot_agent, "edit_trip_itinerary", fake_edit_trip_itinerary)

    response = ChatbotAgent().handle(
        ChatbotMessageRequest(
            message="把第2天行程改轻松一点",
            current_itinerary=original,
        )
    )

    assert response.intent == "update"
    assert captured == {
        "edit_scope": "day_2",
        "instruction": "把第2天行程改轻松一点",
    }
    assert response.updated_itinerary is not None
    assert response.updated_itinerary.days[1].theme == "更轻松的第二天"


def test_chatbot_agent_clarifies_broad_update_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(intent="update"),
    )

    def fail_edit_trip_itinerary(request):
        raise AssertionError("broad update should clarify before editing")

    monkeypatch.setattr(chatbot_agent, "edit_trip_itinerary", fail_edit_trip_itinerary)

    response = ChatbotAgent().handle(
        ChatbotMessageRequest(
            message="帮我把整体行程优化一下",
            current_itinerary=build_itinerary(),
        )
    )

    assert response.intent == "clarify"
    assert "只改某一天" in response.reply


def test_chatbot_agent_searches_with_shared_agency(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="search",
            route_kind="scenic_notice",
            route_query="成都 熊猫基地 今天开放吗 官方公告",
        ),
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            assert max_results == 10
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="景区开放公告",
                        url="https://example.com/open",
                        content="景区今日正常开放，建议以官方渠道为准。",
                        raw_content="景区今日正常开放，建议以官方渠道为准。请关注官方渠道。",
                        published_date="2026-06-23",
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(
            message="帮我查一下熊猫基地今天开放吗？",
            current_itinerary=build_itinerary(),
        )
    )

    assert response.intent == "search"
    assert "景区开放公告" in response.reply
    assert response.sources[0].url == "https://example.com/open"
    assert response.sources[0].raw_content == "景区今日正常开放，建议以官方渠道为准。请关注官方渠道。"


def test_chatbot_agent_answers_weather_with_weather_service(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="search",
            route_kind="weather",
            route_query="明天长沙天气",
        ),
    )

    def fake_weather(city: str):
        assert city == "长沙"
        return {
            "city": "长沙",
            "province": "湖南",
            "report_time": "2026-06-26 10:00:00",
            "days": [
                {
                    "date": "2026-06-26",
                    "week": "5",
                    "day_weather": "多云",
                    "night_weather": "阵雨",
                    "day_temp": "31",
                    "night_temp": "25",
                    "day_wind": "南",
                    "night_wind": "南",
                },
                {
                    "date": "2026-06-27",
                    "week": "6",
                    "day_weather": "小雨",
                    "night_weather": "中雨",
                    "day_temp": "29",
                    "night_temp": "24",
                    "day_wind": "北",
                    "night_wind": "北",
                },
            ],
        }

    class FailingSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            raise AssertionError("weather query should not use generic web search")

    monkeypatch.setattr(
        "app.agents.chatbot_agent.nodes.realtime_query.get_weather_forecast",
        fake_weather,
    )
    monkeypatch.setattr(
        "app.agents.chatbot_agent.nodes.realtime_query.date",
        type(
            "FixedDate",
            (),
            {
                "today": staticmethod(lambda: date(2026, 6, 26)),
            },
        ),
    )

    response = ChatbotAgent(search_agency=FailingSearchAgency()).handle(
        ChatbotMessageRequest(message="明天长沙天气")
    )

    assert response.intent == "search"
    assert "长沙明天天气" in response.reply
    assert "2026-06-27" in response.reply
    assert "白天小雨，夜间中雨" in response.reply
    assert "24~29℃" in response.reply
    assert "2026-06-26 10:00:00" in response.reply
    assert "5月25日" not in response.reply
    assert response.sources == []


def test_chatbot_agent_extracts_city_from_natural_weather_question(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="search",
            route_kind="weather",
            route_query="长沙明天天气",
        ),
    )
    captured: dict[str, str] = {}

    def fake_weather(city: str):
        captured["city"] = city
        return {
            "city": "长沙",
            "report_time": "2026-06-26 10:00:00",
            "days": [
                {
                    "date": "2026-06-27",
                    "day_weather": "小雨",
                    "night_weather": "中雨",
                    "day_temp": "29",
                    "night_temp": "24",
                    "day_wind": "北",
                    "night_wind": "北",
                }
            ],
        }

    monkeypatch.setattr(
        "app.agents.chatbot_agent.nodes.realtime_query.get_weather_forecast",
        fake_weather,
    )
    monkeypatch.setattr(
        "app.agents.chatbot_agent.nodes.realtime_query.date",
        type(
            "FixedDate",
            (),
            {
                "today": staticmethod(lambda: date(2026, 6, 26)),
            },
        ),
    )

    response = ChatbotAgent().handle(ChatbotMessageRequest(message="查长沙明天会下雨吗"))

    assert captured["city"] == "长沙"
    assert "长沙明天天气" in response.reply


def test_chatbot_agent_marks_non_official_search_result_as_unconfirmed(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="search",
            route_kind="scenic_notice",
            route_query="野象谷今天开放吗",
        ),
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="游客经验分享",
                        url="https://example.com/blog",
                        content="网友说景区可能开放，但没有官方公告链接。",
                        raw_content="网友说景区可能开放，但没有官方公告链接。",
                        published_date="2026-06-26",
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="野象谷今天开放吗")
    )

    assert "当前线索" in response.reply
    assert "暂时不足以确认" in response.reply
    assert "## 明确结论\n针对" not in response.reply


def test_chatbot_agent_routes_realtime_search_categories(monkeypatch) -> None:
    queries: list[str] = []

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            queries.append(query)
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title=f"{query} 结果",
                        url=f"https://example.com/{len(queries)}",
                        content=f"{query} 可作为参考，出发前建议再确认官方信息。",
                        raw_content=f"{query} 可作为参考，出发前建议再确认官方信息。",
                        published_date="2026-06-26",
                    )
                ],
            )

    cases = [
        ("野象谷今天开放吗", "scenic_notice", ("官方", "公告", "开放", "闭园", "施工", "预约")),
        ("长沙到西双版纳飞机多久", "transport", ("航班", "飞机", "航司")),
        ("曼听公园门票多少钱", "ticket", ("官方", "门票", "预约")),
        ("告庄夜市营业时间", "business_hours", ("官方", "开放时间", "营业时间", "今日")),
    ]
    for message, route_kind, expected_terms in cases:
        monkeypatch.setattr(
            chatbot_agent,
            "build_chat_llm",
            lambda route_kind=route_kind, message=message: FakeChatLLM(
                intent="search",
                route_kind=route_kind,
                route_query=message,
            ),
        )
        agent = ChatbotAgent(search_agency=FakeSearchAgency())
        response = agent.handle(ChatbotMessageRequest(message=message))
        assert response.intent == "search"
        assert "## 明确结论" in response.reply
        assert "## 来源" in response.reply
        assert all(term in queries[-1] for term in expected_terms)


def test_realtime_transport_answer_uses_12306_mcp_when_available(monkeypatch) -> None:
    fake_llm = FakeChatLLM(
        intent="search",
        route_kind="transport",
        route_query="上海到杭州 明天上午 高铁 直达 不中转",
    )
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            raise AssertionError("12306 MCP 成功时不应降级到网页搜索")

    captured = {}

    def fake_transport_tool(
        message: str,
        search_query: str = "",
        llm=None,
    ) -> TransportToolResult:
        captured["message"] = message
        captured["search_query"] = search_query
        captured["llm"] = llm
        return TransportToolResult(
            available=True,
            answer=(
                "## 明确结论\n"
                "- G205 上海虹桥 07:00 -> 杭州东 07:45，历时 00:45；二等座有，87元\n"
                "- 12306 官方页面为准"
            ),
            source_notes=["2026-06-28 上海到杭州返回 1 条直达车次。"],
            tickets=[
                TrainTicket(
                    train_code="G205",
                    from_station="上海虹桥",
                    to_station="杭州东",
                    start_time="07:00",
                    arrive_time="07:45",
                    duration="00:45",
                    date="2026-06-28",
                )
            ],
        )

    monkeypatch.setattr(
        "app.agents.chatbot_agent.nodes.realtime_query.search_train_tickets_for_agent",
        fake_transport_tool,
    )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="高铁，上海到杭州，明天上午，接受直达优先，不中转")
    )

    assert "G205" in response.reply
    assert "上海虹桥 07:00 -> 杭州东 07:45" in response.reply
    assert "二等座有，87元" in response.reply
    assert "12306 官方页面为准" in response.reply
    assert response.sources[0].title == "中国铁路12306 / 12306 MCP"
    assert response.sources[0].content == "2026-06-28 上海到杭州返回 1 条直达车次。"
    assert response.research_steps[1].title == "查询12306实时余票"
    assert response.research_steps[1].summary == "已获取12306 MCP返回的结构化铁路余票。"
    assert captured == {
        "message": "高铁，上海到杭州，明天上午，接受直达优先，不中转",
        "search_query": "上海到杭州 明天上午 高铁 直达 不中转",
        "llm": fake_llm,
    }


def test_realtime_transport_falls_back_to_web_search_when_12306_fails(monkeypatch) -> None:
    fake_llm = FakeChatLLM(
        intent="search",
        route_kind="transport",
        route_query="上海到杭州 明天上午 高铁 直达 不中转",
        summary=(
            "上海到杭州明天上午优先看上海虹桥到杭州东的直达高铁。"
            "网页搜索只能作为线索，余票仍需以 12306 为准。"
        ),
    )
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)
    monkeypatch.setattr(
        "app.agents.chatbot_agent.nodes.realtime_query.search_train_tickets_for_agent",
        lambda message, search_query="", llm=None: TransportToolResult(
            available=False,
            answer="",
            source_notes=[],
            tickets=[],
            error_message="12306 MCP 未启用。",
        ),
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="上海至杭州火车票查询 - 12306",
                        url="https://www.12306.cn/",
                        content="铁路车票、余票、票价和列车时刻请以铁路12306为准。",
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="高铁，上海到杭州，明天上午，接受直达优先，不中转")
    )

    assert "12306实时查询未完成" in response.reply
    assert "已降级使用网页实时搜索整理线索" in response.reply
    assert "上海虹桥到杭州东" in response.reply
    assert fake_llm.realtime_summary_payload["query_kind"] == "transport"


def test_chatbot_agent_streams_query_plan_and_steps_for_search(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="search",
            route_kind="scenic_notice",
            route_query="野象谷今天开放吗",
        ),
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="官方开放公告",
                        url="https://example.com/open",
                        content="野象谷今日开放，部分区域可能临时调整。",
                        raw_content="野象谷今日开放，部分区域可能临时调整。",
                        published_date="2026-06-26",
                    )
                ],
            )

    events = list(
        ChatbotAgent(search_agency=FakeSearchAgency()).stream(
            ChatbotMessageRequest(message="野象谷今天开放吗")
        )
    )

    assert [event["event"] for event in events] == [
        "intent",
        "query_plan",
        "query_step",
        "query_step",
        "final",
    ]
    assert events[1]["data"][0].id == "classify"
    assert events[2]["data"].status == "running"
    assert events[3]["data"].status == "completed"
    assert events[-1]["data"].research_steps


def test_realtime_router_prefers_second_stage_llm_query(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="search",
            route_kind="ticket",
            route_query="曼听公园 官方门票预约",
        ),
    )
    queries: list[str] = []

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            queries.append(query)
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="门票预约",
                        url="https://example.com/ticket",
                        content="门票信息以官方为准。",
                    )
                ],
            )

    ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="曼听公园门票多少钱")
    )

    assert queries == ["曼听公园 官方门票预约 官方 门票 预约 票价"]


def test_chatbot_agent_stream_yields_before_slow_research_finishes(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(intent="research", route_query="长沙热门景点推荐"),
    )

    class SlowSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            time.sleep(0.2)
            return TavilyResponse(query=query, results=[])

    events = ChatbotAgent(search_agency=SlowSearchAgency()).stream(
        ChatbotMessageRequest(message="长沙热门景点推荐")
    )

    started = time.monotonic()
    first = next(events)
    second = next(events)
    elapsed = time.monotonic() - started

    assert first["event"] == "intent"
    assert second["event"] == "research_plan"
    assert elapsed < 0.15


def test_chatbot_agent_researches_open_travel_recommendation_with_llm_plan(monkeypatch) -> None:
    fake_llm = FakeChatLLM(
        intent="research",
        route_query="长沙热门景点推荐",
        search_queries=[
            "长沙 热门景点 推荐 官方 旅游",
            "长沙 必去景点 游玩时间 门票",
        ],
        generation_tasks=[
            "筛选适合首次到访者的热门景点",
            "按体验类型组织推荐理由",
        ],
        answer_strategy="先确认长沙热门景点信息，再按适合人群和游玩建议给出推荐。",
        summary=(
            "## 我理解你的需求\n你想要长沙热门景点推荐。\n\n"
            "## 我查了哪些信息\n热门景点、门票和游玩建议。\n\n"
            "## 重点结论\n建议优先考虑岳麓山、橘子洲和湖南博物院。"
        ),
    )
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)
    queries: list[str] = []

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            queries.append(query)
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title=f"{query} 结果",
                        url=f"https://example.com/{len(queries)}",
                        content=f"{query} 可作为长沙旅行推荐参考。",
                        raw_content=f"{query} 可作为长沙旅行推荐参考。",
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="长沙热门景点推荐")
    )

    assert fake_llm.intent_invocations == 1
    assert response.intent == "research"
    assert queries[:2] == ["长沙 热门景点 推荐 官方 旅游", "长沙 必去景点 游玩时间 门票"]
    assert response.research_steps[0].id == "understand"
    assert "先确认长沙热门景点信息" in response.research_steps[0].summary
    assert not any(step.id.startswith("generate_") for step in response.research_steps)
    assert response.research_steps[-1].id == "synthesize"
    assert response.research_steps[-1].status == "completed"
    assert "岳麓山" in response.reply


def test_chatbot_agent_remembers_explicit_profile_preferences(monkeypatch) -> None:
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: None)

    response = ChatbotAgent().handle(
        ChatbotMessageRequest(
            message="我们不想早起，少走路，喜欢咖啡和Citywalk，预算尽量控制",
            current_itinerary=build_itinerary(),
        )
    )

    assert response.profile.avoidances == ["不早起", "少走路"]
    assert response.profile.food_preferences == ["咖啡"]
    assert "Citywalk" in response.profile.interests
    assert response.profile.budget_sensitivity == "高"
    assert "用户本轮" in response.conversation_summary


def test_intent_classifier_receives_traveler_profile(monkeypatch) -> None:
    fake_llm = FakeChatLLM(intent="compare")
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)

    decision = ChatbotAgent().classify_intent(
        ChatbotMessageRequest(
            message="帮我比较住春熙路还是宽窄巷子",
            profile={
                "pace_preference": "轻松",
                "avoidances": ["少走路"],
                "interests": ["Citywalk"],
            },
            conversation_summary="用户偏好轻松慢游。",
            current_itinerary=build_itinerary(),
        )
    )

    assert decision.intent == "compare"
    assert fake_llm.intent_payload["traveler_profile"]["pace_preference"] == "轻松"
    assert fake_llm.intent_payload["conversation_summary"] == "用户偏好轻松慢游。"


def test_chatbot_agent_compares_options_with_research_path(monkeypatch) -> None:
    fake_llm = FakeChatLLM(
        intent="compare",
        search_queries=["成都 春熙路 宽窄巷子 住宿 区域 对比"],
        generation_tasks=["按交通、预算、夜生活和少走路偏好比较两个住宿区域"],
        summary="## 对比结论\n如果少走路，春熙路更适合；如果偏人文街区，宽窄巷子更合适。\n\n## 下一步\n先确定你更看重交通还是街区氛围。",
    )
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="成都住宿区域比较",
                        url="https://example.com/compare",
                        content="春熙路交通便利，宽窄巷子更偏人文体验。",
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(
            message="比较住春熙路和宽窄巷子哪个更适合",
            profile={"avoidances": ["少走路"]},
            current_itinerary=build_itinerary(),
        )
    )

    assert response.intent == "compare"
    assert response.research_steps[0].id == "understand"
    assert fake_llm.summary_payload["intent"] == "compare"
    assert fake_llm.summary_payload["traveler_profile"]["avoidances"] == ["少走路"]
    assert "春熙路" in response.reply


def test_chatbot_agent_personalizes_itinerary_with_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(intent="personalize", edit_scope="day_1"),
    )
    original = build_itinerary()
    updated = original.model_copy(deep=True)
    updated.days[0].theme = "轻松少走路慢游"
    captured = {}

    def fake_edit_trip_itinerary(request):
        captured["instruction"] = request.user_instruction
        captured["edit_scope"] = request.edit_scope
        return updated

    monkeypatch.setattr(chatbot_agent, "edit_trip_itinerary", fake_edit_trip_itinerary)

    response = ChatbotAgent().handle(
        ChatbotMessageRequest(
            message="按我的偏好重排一下",
            profile={
                "pace_preference": "轻松",
                "avoidances": ["少走路", "不早起"],
                "food_preferences": ["咖啡"],
            },
            current_itinerary=original,
        )
    )

    assert response.intent == "personalize"
    assert response.updated_itinerary is not None
    assert response.updated_itinerary.days[0].theme == "轻松少走路慢游"
    assert captured["edit_scope"] == "day_1"
    assert "旅行偏好画像" in captured["instruction"]
    assert "少走路" in captured["instruction"]


def test_chatbot_agent_personalize_requires_profile_before_update(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(intent="personalize"),
    )

    def fail_edit_trip_itinerary(request):
        raise AssertionError("empty-profile personalization should clarify before editing")

    monkeypatch.setattr(chatbot_agent, "edit_trip_itinerary", fail_edit_trip_itinerary)

    response = ChatbotAgent().handle(
        ChatbotMessageRequest(
            message="按我的偏好重排一下",
            current_itinerary=build_itinerary(),
        )
    )

    assert response.intent == "clarify"
    assert "少走路" in response.reply


def test_chatbot_agent_streams_visible_plan_for_clarify(monkeypatch) -> None:
    fake_llm = FakeChatLLM(
        intent="clarify",
        answer_strategy="信息不足，先询问目的地、日期、人数、预算和偏好。",
    )
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)

    events = list(ChatbotAgent().stream(ChatbotMessageRequest(message="帮我安排一下")))

    assert [event["event"] for event in events] == ["intent", "research_plan", "final"]
    assert events[1]["data"][0].id == "understand"
    assert events[1]["data"][0].status == "completed"
    assert "信息不足" in events[1]["data"][0].summary
    assert events[-1]["data"].intent == "clarify"


def test_chatbot_agent_researches_multi_step_travel_question(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="research",
            route_query="西双版纳 下周 旅行注意事项",
            search_queries=[
                "西双版纳 下周 天气",
                "西双版纳 景区 开放公告",
                "长沙 西双版纳 交通",
                "西双版纳 旅游 安全",
                "西双版纳 雨季 装备",
            ],
        ),
    )
    queries: list[str] = []

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            queries.append(query)
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title=f"{query} 查询结果",
                        url=f"https://example.com/{len(queries)}",
                        content=f"{query} 需要出发前再次确认官方信息。",
                        raw_content=f"{query} 需要出发前再次确认官方信息。",
                        published_date="2026-06-24",
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(
            message="我下周想去西双版纳，从长沙出发，以及买好往返车票，需要注意什么",
        )
    )

    assert response.intent == "research"
    assert len(response.research_steps) >= 5
    assert any("天气" in step.title for step in response.research_steps)
    assert any("景区" in step.title for step in response.research_steps)
    assert any("交通" in step.title for step in response.research_steps)
    assert len(queries) >= 4
    assert "我理解你的需求" in response.reply
    assert "西双版纳 下周 天气" in response.reply
    assert "长沙 西双版纳 交通" in response.reply
    assert response.sources[0].url == "https://example.com/1"


def test_chatbot_agent_research_handles_search_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="research",
            route_query="成都 下周 行程风险",
        ),
    )

    class FailingSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            raise RuntimeError("search unavailable")

    response = ChatbotAgent(search_agency=FailingSearchAgency()).handle(
        ChatbotMessageRequest(
            message="帮我检查一下下周成都行程天气和景区公告风险",
            current_itinerary=build_itinerary(),
        )
    )

    assert response.intent == "research"
    assert response.research_steps
    assert any(step.status == "failed" for step in response.research_steps)
    assert "部分信息暂时无法查证" in response.reply


def test_chatbot_agent_research_finalizes_when_summary_llm_times_out(monkeypatch) -> None:
    class TimeoutSummaryLLM(FakeChatLLM):
        def invoke(self, messages):
            system = messages[0][1]
            if "只根据用户问题和本轮搜索证据" in system:
                time.sleep(0.05)
                return FakeResponse("")
            return super().invoke(messages)

    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: TimeoutSummaryLLM(
            intent="research",
            route_query="长沙热门景点推荐",
            search_queries=["长沙 热门景点 推荐"],
        ),
    )
    monkeypatch.setattr(
        "app.agents.chatbot_agent.nodes.research_node.RESEARCH_SUMMARY_TIMEOUT_SECONDS",
        0.01,
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="长沙景点推荐",
                        url="https://example.com/changsha",
                        content="岳麓山、橘子洲和湖南博物院是热门景点。",
                    )
                ],
            )

    events = list(
        ChatbotAgent(search_agency=FakeSearchAgency()).stream(
            ChatbotMessageRequest(message="长沙热门景点推荐")
        )
    )

    assert events[-1]["event"] == "final"
    assert "当前 LLM 总结不可用" in events[-1]["data"].reply
    assert "长沙 热门景点 推荐" in events[-1]["data"].reply


def test_chatbot_agent_research_fallback_matches_scenic_recommendation_question(monkeypatch) -> None:
    class SummaryLLM(FakeChatLLM):
        def invoke(self, messages):
            system = messages[0][1]
            if "只根据用户问题和本轮搜索证据" in system:
                return FakeResponse(
                    "## 长沙热门景点推荐\n"
                    "- 岳麓山：适合自然休闲和岳麓书院人文线，建议预留半天。\n"
                    "- 橘子洲：适合江景散步和城市地标打卡，出发前确认预约要求。\n"
                    "- 湖南博物院：适合历史文化和室内参观，建议提前预约。\n"
                    "- 杜甫江阁和太平街/坡子街：适合夜景和美食补充安排。"
                )
            return super().invoke(messages)

    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: SummaryLLM(
            intent="research",
            route_query="长沙热门景点推荐",
            search_queries=[
                "长沙热门景点推荐 2025",
                "长沙 必去景点 官方",
                "长沙 岳麓山 橘子洲 湖南博物院 开放时间",
            ],
            generation_tasks=[
                "按地标人文、自然休闲、亲子打卡、夜游美食四类整理热门景点",
                "为每个景点生成推荐理由、停留时长、门票预约提示",
            ],
            answer_strategy="先联网查询长沙热门景点及近期开放信息，再按景点类型与适合人群生成分层推荐。",
        ),
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="长沙景点攻略汇总",
                        url="https://example.com/changsha-spots",
                        content="橘子洲景区开放时间为每天7:00-22:00；岳麓山景区6:00-22:00；湖南博物院每周二至周日9:00-17:00。",
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="长沙热门景点推荐")
    )

    assert "## 长沙热门景点推荐" in response.reply
    assert "岳麓山" in response.reply
    assert "橘子洲" in response.reply
    assert "湖南博物院" in response.reply
    assert "查询依据：" not in response.reply
    assert "出发前检查清单" not in response.reply
    assert "实时风险和准备事项" not in response.reply


def test_research_fallback_uses_beijing_search_evidence_without_fixed_spots(monkeypatch) -> None:
    class SummaryLLM(FakeChatLLM):
        def invoke(self, messages):
            system = messages[0][1]
            if "只根据用户问题和本轮搜索证据" in system:
                return FakeResponse(
                    "## 北京热门景点推荐\n"
                    "- 故宫博物院：首次到访优先级最高，需提前确认预约和开放时间。\n"
                    "- 天安门广场：适合与故宫、前门串联，按官方要求预约并带证件。\n"
                    "- 颐和园、八达岭长城、天坛公园：根据体力和停留天数取舍。"
                )
            return super().invoke(messages)

    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: SummaryLLM(
            intent="research",
            route_query="北京热门景点推荐",
            search_queries=[
                "北京热门景点推荐 2025",
                "北京 故宫 开放时间 预约",
                "北京 天安门广场 预约 参观",
            ],
        ),
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            content_by_query = {
                "北京热门景点推荐 2025": "北京首次到访可优先考虑故宫博物院、天安门广场、颐和园、八达岭长城和天坛公园。",
                "北京 故宫 开放时间 预约": "故宫博物院参观通常需要提前预约，出发前应确认官方开放时间和余票。",
                "北京 天安门广场 预约 参观": "天安门广场参观需按官方要求预约并携带有效证件。",
            }
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title=f"{query} 结果",
                        url=f"https://example.com/{len(query)}",
                        content=content_by_query[query],
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="北京热门景点推荐")
    )

    assert "故宫博物院" in response.reply
    assert "天安门广场" in response.reply
    assert "岳麓山" not in response.reply
    assert "橘子洲" not in response.reply
    assert "湖南博物院" not in response.reply


def test_research_steps_use_llm_queries_without_fixed_fillers() -> None:
    request = ChatbotMessageRequest(
        message="从武汉去长沙热门景点的出行方案，两天时间",
    )
    decision = IntentDecision(
        intent="research",
        reason="测试动态查询列表",
        search_queries=[
            "武汉到长沙 高铁 时长 班次",
            "长沙 两天 热门景点 路线",
        ],
        generation_tasks=[
            "按两天节奏组织出行方案",
            "结合查询结果筛选景点",
        ],
    )

    steps = build_research_steps(request, decision)
    searchable_steps = [step for step in steps if step.query]

    assert [step.query for step in searchable_steps] == decision.search_queries
    assert not any(step.id.startswith("generate_") for step in steps)
    assert "天气" not in searchable_steps[0].title


def test_research_default_queries_follow_question_without_unrelated_weather() -> None:
    request = ChatbotMessageRequest(
        message="从武汉去长沙热门景点的出行方案，两天时间",
    )
    decision = IntentDecision(
        intent="research",
        reason="测试默认动态查询",
        search_query="从武汉去长沙 两天 热门景点 出行方案",
    )

    steps = build_research_steps(request, decision)
    queries = [step.query for step in steps if step.query]

    assert any(query.startswith("武汉到长沙 高铁") for query in queries)
    assert any("长沙" in query and "两天" in query and "景点" in query for query in queries)
    assert any("预约" in query for query in queries)
    assert not any("天气" in query for query in queries)
    assert not any("防晒" in query or "防蚊" in query for query in queries)


def test_chatbot_agent_streams_synthesis_only_after_queries_complete(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="research",
            route_query="武汉到长沙 两天 景点方案",
            search_queries=[
                "武汉到长沙 高铁 时长 班次",
                "长沙 两天 热门景点 路线",
            ],
            generation_tasks=["结合交通和景点查询结果生成两天方案"],
            summary="## 两天方案\n第 1 天岳麓山和橘子洲，第 2 天湖南博物院后返程。",
        ),
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title=f"{query} 结果",
                        url=f"https://example.com/{query}",
                        content=f"{query} 的实时查询摘要。",
                    )
                ],
            )

    events = list(
        ChatbotAgent(search_agency=FakeSearchAgency()).stream(
            ChatbotMessageRequest(message="从武汉去长沙热门景点的出行方案，两天时间")
        )
    )

    plan = next(event["data"] for event in events if event["event"] == "research_plan")
    assert not any(step.id.startswith("generate_") for step in plan)
    assert all(step.id != "synthesize" for step in plan)

    synthesis_events = [
        event["data"]
        for event in events
        if event["event"] == "research_step" and event["data"].id == "synthesize"
    ]
    assert [step.status for step in synthesis_events] == ["running", "completed"]
    assert events[-1]["data"].research_steps[-1].id == "synthesize"


def test_research_summary_llm_receives_source_evidence(monkeypatch) -> None:
    fake_llm = FakeChatLLM(
        intent="research",
        search_queries=["长沙 岳麓山 橘子洲 湖南博物院 开放时间 预约"],
        summary="## 建议\n优先岳麓山、橘子洲和湖南博物院，预约以官方为准。",
    )
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="长沙景区预约入口汇总",
                        url="https://example.com/reservation",
                        content="橘子洲、岳麓山需要预约，湖南博物院可提前预约。",
                        published_date="2026-06-25",
                    )
                ],
            )

    ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="长沙热门景点怎么安排")
    )

    evidence = fake_llm.summary_payload["source_evidence"]
    assert evidence[0]["query"] == "长沙 岳麓山 橘子洲 湖南博物院 开放时间 预约"
    assert evidence[0]["sources"][0]["content"] == "橘子洲、岳麓山需要预约，湖南博物院可提前预约。"
    assert fake_llm.summary_payload["traveler_profile"] == {
        "pace_preference": None,
        "food_preferences": [],
        "avoidances": [],
        "interests": [],
        "budget_sensitivity": None,
        "confirmed_facts": [],
    }


def test_research_summary_uses_single_compact_prompt_with_truncated_evidence(monkeypatch) -> None:
    class CapturingSummaryLLM(FakeChatLLM):
        def invoke(self, messages):
            system = messages[0][1]
            if "只根据用户问题和本轮搜索证据" in system:
                self.summary_payload = json.loads(messages[1][1])
                return FakeResponse("## 建议\n按查询证据安排。")
            if "专业旅行顾问" in system:
                raise AssertionError("research summary should not send the full prompt first")
            return super().invoke(messages)

    fake_llm = CapturingSummaryLLM(
        intent="research",
        search_queries=["长沙 热门景点 推荐"],
    )
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: fake_llm)

    long_content = "岳麓山" + "很适合慢游" * 120

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title="长沙景点推荐",
                        url="https://example.com/1",
                        content=long_content,
                    ),
                    SearchResult(
                        title="长沙预约提示",
                        url="https://example.com/2",
                        content="橘子洲和湖南博物院建议提前确认预约。",
                    ),
                    SearchResult(
                        title="不应进入总结 payload",
                        url="https://example.com/3",
                        content="第三条证据不应进入总结 payload。",
                    ),
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="长沙热门景点推荐")
    )

    sources = fake_llm.summary_payload["source_evidence"][0]["sources"]
    assert response.reply == "## 建议\n按查询证据安排。"
    assert len(sources) == 2
    assert len(sources[0]["content"]) <= 503
    assert sources[0]["content"].endswith("...")
    assert sources[1]["title"] == "长沙预约提示"


def test_research_fallback_uses_search_records_for_two_day_plan(monkeypatch) -> None:
    class EmptyPrimarySummaryLLM(FakeChatLLM):
        def invoke(self, messages):
            system = messages[0][1]
            if "source_evidence 和每个调研步骤" in system:
                return FakeResponse("")
            if "只根据用户问题和本轮搜索证据" in system:
                return FakeResponse(
                    "## 两天方案\n"
                    "- 交通建议：武汉到长沙南高铁约1小时30分钟，早班车较多。\n"
                    "- 第 1 天：岳麓山、岳麓书院和橘子洲。\n"
                    "- 第 2 天：湖南博物院、太平街后返程。"
                )
            return super().invoke(messages)

    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: EmptyPrimarySummaryLLM(
            intent="research",
            route_query="武汉到长沙 两天 热门景点",
            search_queries=[
                "武汉到长沙 高铁 时长 班次",
                "长沙 两天 热门景点 路线",
                "岳麓山 橘子洲 湖南博物院 开放时间 预约",
            ],
        ),
    )

    class FakeSearchAgency:
        def basic_search_news(self, query: str, max_results: int = 5) -> TavilyResponse:
            content_by_query = {
                "武汉到长沙 高铁 时长 班次": "武汉到长沙南高铁约1小时30分钟，早班车较多。",
                "长沙 两天 热门景点 路线": "两日路线可安排岳麓山、岳麓书院、橘子洲、湖南博物院、太平街。",
                "岳麓山 橘子洲 湖南博物院 开放时间 预约": "橘子洲、岳麓山免费但通常需要预约；湖南博物院需提前预约。",
            }
            return TavilyResponse(
                query=query,
                results=[
                    SearchResult(
                        title=f"{query} 结果",
                        url=f"https://example.com/{len(query)}",
                        content=content_by_query[query],
                    )
                ],
            )

    response = ChatbotAgent(search_agency=FakeSearchAgency()).handle(
        ChatbotMessageRequest(message="从武汉去长沙热门景点的出行方案，两天时间")
    )

    assert "第 1 天" in response.reply
    assert "第 2 天" in response.reply
    assert "武汉到长沙南高铁约1小时30分钟" in response.reply
    assert "岳麓山" in response.reply
    assert "可作为长沙热门景点候选" not in response.reply


def test_chatbot_agent_keeps_single_point_query_as_search_with_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: FakeChatLLM(
            intent="search",
            route_kind="scenic_notice",
            route_query="成都 熊猫基地 今天开放吗",
        ),
    )

    decision = ChatbotAgent().classify_intent(
        ChatbotMessageRequest(
            message="帮我查一下熊猫基地今天开放吗？",
            current_itinerary=build_itinerary(),
        )
    )

    assert decision.intent == "search"


def test_chatbot_agent_without_llm_does_not_keyword_route(monkeypatch) -> None:
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: None)

    decision = ChatbotAgent().classify_intent(
        ChatbotMessageRequest(
            message="帮我查一下熊猫基地今天开放吗？",
            current_itinerary=build_itinerary(),
        )
    )

    assert decision.intent == "ask"
    assert "未使用关键词规则" in decision.reason


def test_destination_search_uses_shared_web_search_service() -> None:
    from app.agents.destination_intelligence_agent.tools.search import TavilyNewsAgency
    from app.integrations.web_search import TavilyNewsAgency as SharedAgency

    assert TavilyNewsAgency is SharedAgency


def test_chatbot_message_api_returns_agent_response(monkeypatch) -> None:
    def fake_handle(request):
        assert request.message == "这个行程大概几天？"
        return {
            "intent": "ask",
            "reply": "这是一个两天行程。",
            "reason": "测试",
            "updated_itinerary": None,
            "sources": [],
        }

    monkeypatch.setattr("app.api.routes.chatbot.handle_chatbot_message", fake_handle)

    client = TestClient(app)
    response = client.post(
        "/chatbot/message",
        json={
            "message": "这个行程大概几天？",
            "current_itinerary": build_itinerary().model_dump(mode="json"),
            "history": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "ask"
    assert response.json()["reply"] == "这是一个两天行程。"
    assert response.json()["research_steps"] == []


def test_chatbot_message_stream_returns_research_progress(monkeypatch) -> None:
    class FakeAgent:
        def stream(self, request):
            assert request.message == "我下周想去西双版纳，需要注意什么"
            yield {
                "event": "intent",
                "data": IntentDecision(intent="research", reason="需要多步实时查询"),
            }
            yield {
                "event": "research_step",
                "data": {
                    "id": "weather",
                    "title": "查询天气和穿衣建议",
                    "status": "running",
                    "query": "西双版纳 下周 天气",
                    "summary": "",
                    "sources": [],
                },
            }
            yield {
                "event": "final",
                "data": {
                    "intent": "research",
                    "reply": "## 结论\n建议带雨具。",
                    "reason": "测试",
                    "updated_itinerary": None,
                    "sources": [],
                    "research_steps": [
                        {
                            "id": "weather",
                            "title": "查询天气和穿衣建议",
                            "status": "completed",
                            "query": "西双版纳 下周 天气",
                            "summary": "近期多雨。",
                            "sources": [],
                        }
                    ],
                },
            }

    monkeypatch.setattr("app.api.routes.chatbot.ChatbotAgent", lambda: FakeAgent())

    client = TestClient(app)
    with client.stream(
        "POST",
        "/chatbot/message/stream",
        json={"message": "我下周想去西双版纳，需要注意什么", "history": []},
    ) as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: intent" in body
    assert '"intent":"research"' in body
    assert "event: research_step" in body
    assert '"status":"running"' in body
    assert "event: final" in body
    assert "## 结论" in body


def test_chatbot_message_stream_returns_query_progress(monkeypatch) -> None:
    class FakeAgent:
        def stream(self, request):
            assert request.message == "野象谷今天开放吗"
            yield {
                "event": "intent",
                "data": IntentDecision(intent="search", reason="需要实时查询"),
            }
            yield {
                "event": "query_plan",
                "data": [
                    {
                        "id": "classify",
                        "title": "识别实时查询类型",
                        "status": "completed",
                        "query": None,
                        "summary": "已识别为：景区公告查询。",
                        "sources": [],
                    }
                ],
            }
            yield {
                "event": "query_step",
                "data": {
                    "id": "query",
                    "title": "查询景区官方公告",
                    "status": "running",
                    "query": "野象谷今天开放吗 官方 公告 开放 闭园 施工 预约",
                    "summary": "",
                    "sources": [],
                },
            }
            yield {
                "event": "final",
                "data": {
                    "intent": "search",
                    "reply": "## 明确结论\n以官方公告为准。",
                    "reason": "测试",
                    "updated_itinerary": None,
                    "sources": [],
                    "research_steps": [],
                },
            }

    monkeypatch.setattr("app.api.routes.chatbot.ChatbotAgent", lambda: FakeAgent())

    client = TestClient(app)
    with client.stream(
        "POST",
        "/chatbot/message/stream",
        json={"message": "野象谷今天开放吗", "history": []},
    ) as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert "event: query_plan" in body
    assert "event: query_step" in body
    assert "查询景区官方公告" in body
    assert "event: final" in body
