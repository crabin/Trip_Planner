from __future__ import annotations

from fastapi.testclient import TestClient

from app.agents.chatbot_agent import agent as chatbot_agent
from app.agents.chatbot_agent.agent import ChatbotAgent
from app.api.main import app
from app.models.schemas import (
    BudgetBreakdown,
    ChatbotMessageRequest,
    DayPlan,
    Itinerary,
    MealItem,
    SpotItem,
)
from app.services.web_search_service import SearchResult, TavilyResponse


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
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: None)
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


def test_chatbot_agent_searches_with_shared_agency(monkeypatch) -> None:
    monkeypatch.setattr(chatbot_agent, "build_chat_llm", lambda: None)

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


def test_destination_search_uses_shared_web_search_service() -> None:
    from app.agents.destination_intelligence_agent.tools.search import TavilyNewsAgency
    from app.services.web_search_service import TavilyNewsAgency as SharedAgency

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
