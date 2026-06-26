from __future__ import annotations

from datetime import date
import json
import time

from fastapi.testclient import TestClient

from app.agents.chatbot_agent import agent as chatbot_agent
from app.agents.chatbot_agent.agent import ChatbotAgent
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
from app.integrations.web_search import SearchResult, TavilyResponse


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
        self.summary_payload = {}

    def invoke(self, messages):
        system = messages[0][1]
        if "实时查询路由器" in system:
            return FakeResponse(
                (
                    '{"query_kind":"%s","search_query":"%s","reason":"测试路由"}'
                    % (self.route_kind, self.route_query or "")
                )
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
    assert any(step.id.startswith("generate_") for step in response.research_steps)
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
            if "专业旅行顾问" in system:
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
    assert events[-1]["data"].reply
    assert "长沙热门景点推荐" in events[-1]["data"].reply


def test_chatbot_agent_research_fallback_matches_scenic_recommendation_question(monkeypatch) -> None:
    class EmptySummaryLLM(FakeChatLLM):
        def invoke(self, messages):
            system = messages[0][1]
            if "专业旅行顾问" in system:
                return FakeResponse("")
            return super().invoke(messages)

    monkeypatch.setattr(
        chatbot_agent,
        "build_chat_llm",
        lambda: EmptySummaryLLM(
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

    assert "## 推荐建议" in response.reply
    assert "岳麓山" in response.reply
    assert "橘子洲" in response.reply
    assert "湖南博物院" in response.reply
    assert "出发前检查清单" not in response.reply
    assert "实时风险和准备事项" not in response.reply


def test_research_steps_fill_missing_queries_from_defaults() -> None:
    request = ChatbotMessageRequest(
        message="我下周想去厦门，需要注意什么？",
    )
    decision = IntentDecision(
        intent="research",
        reason="测试短查询列表",
        search_queries=["厦门 下周 天气"],
    )

    steps = build_research_steps(request, decision)
    searchable_steps = [step for step in steps if step.query]

    assert len(searchable_steps) == 5
    assert searchable_steps[0].query == "厦门 下周 天气"
    assert all(step.query for step in searchable_steps)


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
