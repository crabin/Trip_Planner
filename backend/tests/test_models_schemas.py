from pathlib import Path
import sys

import pytest
from pydantic import ValidationError


# Allow direct imports from backend/app when running tests from this file.
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    ChatbotMessageRequest,
    ChatbotMessageResponse,
    DayPlan,
    HotelItem,
    Itinerary,
    MealItem,
    SpotItem,
    TransportItem,
    TripEditRequest,
    TripRequest,
    TripSaveRequest,
    TravelerProfile,
)
from app.services.itinerary_display_service import attach_itinerary_display  # noqa: E402


def build_trip_request() -> TripRequest:
    '''构建一个示例 TripRequest 对象，用于测试'''
    return TripRequest(
        destination="大理",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        preferences=["自然风景", "拍照", "美食"],
        pace="轻松",
        dietary_preferences=["少辣"],
        hotel_level="舒适型",
        special_notes="不想太早起床，希望能安排看日落。",
    )


def build_itinerary() -> Itinerary:
    '''构建一个示例 Itinerary 对象，用于测试'''
    day_one = DayPlan(
        day_index=1,
        date="2026-04-10",
        theme="古城慢游",
        spots=[
            SpotItem(
                name="大理古城",
                start_time="10:00",
                end_time="12:00",
                description="先在古城慢慢逛，适应旅行节奏。",
                estimated_cost=0,
                location="大理古城",
            )
        ],
        meals=[
            MealItem(
                name="古城米线店",
                meal_type="午餐",
                estimated_cost=60,
                notes="口味可选清淡。",
            )
        ],
        hotel=HotelItem(
            name="古城舒适型民宿",
            level="舒适型",
            estimated_cost=280,
            location="大理古城附近",
        ),
        transport=[
            TransportItem(
                mode="打车",
                from_place="大理站",
                to_place="大理古城",
                estimated_cost=35,
                duration="40 分钟",
            )
        ],
        notes=["第一天尽量轻松，不安排太赶。"],
    )

    return Itinerary(
        trip_id="trip_dali_demo_001",
        destination="大理",
        summary="适合两人轻松游玩的 3 日行程示例。",
        days=[day_one],
        estimated_budget=1550,
        budget_breakdown=BudgetBreakdown(
            transport=335,
            hotel=640,
            meals=180,
            tickets=120,
            other=275,
            total=1550,
        ),
        tips=["早晚温差较大，建议带薄外套。"],
        source_notes=["该结果目前是 Day 2 的手工演示数据。"],
    )


def test_trip_request_can_be_created_successfully() -> None:
    '''测试 TripRequest 模型能否成功创建'''
    request = build_trip_request()

    assert request.destination == "大理"
    assert request.travelers == 2
    assert request.budget == 3200
    assert request.preferences == ["自然风景", "拍照", "美食"]
    assert request.deep_planning_reflection_rounds == 2
    assert request.deep_planning_search_engine == "tavily"


def test_trip_request_accepts_deep_planning_settings() -> None:
    request = TripRequest(
        destination="大理",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        deep_planning_reflection_rounds=4,
        deep_planning_search_engine="searxng",
    )

    assert request.deep_planning_reflection_rounds == 4
    assert request.deep_planning_search_engine == "searxng"


def test_chatbot_schemas_accept_traveler_profile_and_new_intents() -> None:
    profile = TravelerProfile(
        pace_preference="轻松",
        food_preferences=["少辣", "咖啡"],
        avoidances=["不早起"],
        interests=["Citywalk"],
        budget_sensitivity="高",
        confirmed_facts=["我们带老人同行"],
    )
    request = ChatbotMessageRequest(
        message="按我的偏好重排行程",
        profile=profile,
        conversation_summary="用户喜欢轻松节奏。",
    )
    response = ChatbotMessageResponse(
        intent="personalize",
        reply="已按轻松节奏调整。",
        reason="测试",
        profile=request.profile,
        conversation_summary=request.conversation_summary,
    )

    assert request.profile.avoidances == ["不早起"]
    assert response.intent == "personalize"
    assert response.profile.food_preferences == ["少辣", "咖啡"]


def test_trip_request_rejects_invalid_deep_planning_settings() -> None:
    with pytest.raises(ValidationError):
        TripRequest(
            destination="大理",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=2,
            budget=3200,
            deep_planning_reflection_rounds=6,
        )

    with pytest.raises(ValidationError):
        TripRequest(
            destination="大理",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=2,
            budget=3200,
            deep_planning_search_engine="browser",
        )


def test_trip_request_rejects_invalid_travelers() -> None:
    '''测试 TripRequest 模型在 travelers 字段为 0 时会抛出 ValidationError'''
    with pytest.raises(ValidationError):
        TripRequest(
            destination="大理",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=0,
            budget=3200,
        )


def test_trip_request_rejects_end_date_before_start_date() -> None:
    with pytest.raises(ValidationError):
        TripRequest(
            destination="大理",
            start_date="2026-04-12",
            end_date="2026-04-10",
            travelers=2,
            budget=3200,
        )


def test_trip_request_rejects_negative_budget() -> None:
    '''测试 TripRequest 模型在 budget 字段为负数时会抛出 ValidationError'''
    with pytest.raises(ValidationError):
        TripRequest(
            destination="大理",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=2,
            budget=-1,
        )


def test_itinerary_can_be_created_successfully() -> None:
    '''测试 Itinerary 模型能否成功创建'''
    itinerary = build_itinerary()

    assert itinerary.trip_id == "trip_dali_demo_001"
    assert itinerary.destination == "大理"
    assert len(itinerary.days) == 1
    assert itinerary.days[0].theme == "古城慢游"
    assert itinerary.budget_breakdown.total == 1550


def test_itinerary_display_json_is_structured_for_result_page_updates() -> None:
    '''测试 itinerary 可以生成解耦的结果页展示 JSON。'''
    itinerary = attach_itinerary_display(build_itinerary())

    assert itinerary.display is not None
    assert itinerary.display.version == "itinerary-display-v1"
    assert itinerary.display.title == "大理旅行计划"
    assert itinerary.display.overview[0].key == "date_range"
    assert itinerary.display.tip_items[0].key == "tip_1"
    assert itinerary.display.tip_items[0].checked is False
    assert itinerary.display.tip_items[0].source_path == "tips.0"
    assert itinerary.display.budget_items[0].source_path == "budget_breakdown.tickets"
    assert itinerary.display.map_points[0].source_path == "days.0.spots.0"
    assert itinerary.display.day_cards[0].fields[0].source_path == "days.0.spots.0.name"
    assert {section.key for section in itinerary.display.sections} >= {
        "overview",
        "budget",
        "tips",
        "map",
        "daily_plan",
    }


def test_itinerary_display_tips_are_prioritized_and_limited() -> None:
    '''测试结果页旅行提示只展示少量高优先级检查项。'''
    itinerary = build_itinerary()
    itinerary.tips = [
        "手机、相机、充电宝充满",
        "今晚住宿优先订大理古城南门/西门外、可打车到门口、舒适型双床/大床房",
        "出发前复核天气与逐小时降雨",
        "若06-25返程已知，先收藏返程站点与酒店定位",
        "只锁1顿重点晚餐，其余餐饮现场机动更稳",
        "保存酒店地址、电话、订单截图",
        "如去苍山，复核索道官方运营状态",
        "带齐雨具、防晒、薄外套",
        "若走海东线，提前锁返程车或考虑包车",
        "今晚住宿优先订大理古城南门/西门外、可打车到门口、舒适型双床/大床房",
    ]

    itinerary = attach_itinerary_display(itinerary)

    assert itinerary.display is not None
    assert itinerary.display.tips == [
        "今晚住宿优先订大理古城南门/西门外、可打车到门口、舒适型双床/大床房",
        "若06-25返程已知，先收藏返程站点与酒店定位",
        "若走海东线，提前锁返程车或考虑包车",
        "出发前复核天气与逐小时降雨",
        "带齐雨具、防晒、薄外套",
    ]
    assert len(itinerary.display.tip_items) == 5


def test_day_plan_contains_nested_objects() -> None:
    '''测试 DayPlan 模型中的嵌套对象是否正确创建'''
    itinerary = build_itinerary()
    first_day = itinerary.days[0]

    assert isinstance(first_day.spots[0], SpotItem)
    assert isinstance(first_day.meals[0], MealItem)
    assert isinstance(first_day.hotel, HotelItem)
    assert isinstance(first_day.transport[0], TransportItem)


def test_trip_edit_request_can_wrap_existing_itinerary() -> None:
    '''测试 TripEditRequest 模型能否正确包装一个已存在的 Itinerary'''
    itinerary = build_itinerary()

    edit_request = TripEditRequest(
        trip_id=itinerary.trip_id,
        current_itinerary=itinerary,
        user_instruction="第二天改轻松一点",
        edit_scope="day_2",
        preserve_constraints=["保留轻松节奏"],
    )

    assert edit_request.trip_id == "trip_dali_demo_001"
    assert edit_request.current_itinerary.destination == "大理"
    assert edit_request.user_instruction == "第二天改轻松一点"


def test_trip_save_request_can_hold_full_itinerary() -> None:
    '''测试 TripSaveRequest 模型能否正确持有一个完整的 Itinerary'''
    itinerary = build_itinerary()

    save_request = TripSaveRequest(
        trip_id=itinerary.trip_id,
        itinerary=itinerary,
        user_id="user_001",
    )

    assert save_request.trip_id == "trip_dali_demo_001"
    assert save_request.itinerary.summary == "适合两人轻松游玩的 3 日行程示例。"
    assert save_request.user_id == "user_001"
