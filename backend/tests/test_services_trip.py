from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


# 允许测试文件直接导入 backend/app 下的模块。
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import TripEditRequest, TripRequest  # noqa: E402
from app.services.trip_service import edit_trip_itinerary, generate_trip_itinerary  # noqa: E402
import app.services.trip_service as trip_service  # noqa: E402


@pytest.fixture(autouse=True)
def default_to_rule_based_generation(monkeypatch) -> None:
    """避免 service 单测因本机真实 LLM 配置变成慢速集成测试。"""
    monkeypatch.setattr(trip_service, "generate_planner_draft", lambda *args, **kwargs: None)


'''
给一个 TripRequest，service 会不会正确返回 Itinerary。

测试内容：
    能接收 TripRequest
    能返回结构正确的 Itinerary
    能根据日期和偏好生成合理的演示结果
'''
def build_trip_request() -> TripRequest:
    """构造一个合法的 TripRequest，供 service 测试复用。"""
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
        special_notes="不想太早起床，希望安排一个适合看日落的地点",
    )


def test_generate_trip_itinerary_returns_itinerary_object() -> None:
    """测试 service 能返回一个结构完整的 itinerary。"""
    request = build_trip_request()

    itinerary = generate_trip_itinerary(request)

    assert itinerary.destination == "大理"
    assert itinerary.trip_id.startswith("trip_")
    assert itinerary.summary != ""
    assert len(itinerary.days) == 3
    assert itinerary.budget_breakdown.total >= 0


def test_generate_trip_itinerary_builds_day_plans_by_date_range() -> None:
    """测试 service 会根据日期范围生成对应天数的 DayPlan。"""
    request = build_trip_request()

    itinerary = generate_trip_itinerary(request)

    assert len(itinerary.days) == 3
    assert itinerary.days[0].day_index == 1
    assert itinerary.days[1].day_index == 2
    assert itinerary.days[2].day_index == 3


def test_generate_trip_itinerary_keeps_request_preferences_in_summary() -> None:
    """测试用户偏好会被写入返回摘要中。"""
    request = build_trip_request()

    itinerary = generate_trip_itinerary(request)

    assert "自然风景" in itinerary.summary
    assert "拍照" in itinerary.summary
    assert "美食" in itinerary.summary

'''
测的是：
    service 能不能基于旧 Itinerary 做修改
    edit_scope="day_2" 是否真的改到第二天
    用户指令是否真的影响结果
'''
def test_edit_trip_itinerary_updates_target_day_theme(monkeypatch) -> None:
    """测试编辑逻辑可以修改指定天数的主题与备注。"""
    monkeypatch.setattr(trip_service, "generate_day_edit_draft", lambda request, target_day: None)
    original_itinerary = generate_trip_itinerary(build_trip_request())

    edit_request = TripEditRequest(
        trip_id=original_itinerary.trip_id,
        current_itinerary=original_itinerary,
        user_instruction="第二天改得更轻松一点",
        edit_scope="day_2",
        preserve_constraints=["保留预算结构"],
    )

    updated_itinerary = edit_trip_itinerary(edit_request)

    assert updated_itinerary.days[1].theme.endswith("（已调整为更轻松）")
    assert "已根据用户要求把节奏调整得更轻松。" in updated_itinerary.days[1].notes


def test_edit_trip_itinerary_can_replace_first_spot_with_free_time(monkeypatch) -> None:
    """测试“不要安排”指令会把景点调整成自由活动。"""
    monkeypatch.setattr(trip_service, "generate_day_edit_draft", lambda request, target_day: None)
    original_itinerary = generate_trip_itinerary(build_trip_request())

    edit_request = TripEditRequest(
        trip_id=original_itinerary.trip_id,
        current_itinerary=original_itinerary,
        user_instruction="第二天不要安排景点了",
        edit_scope="day_2",
        preserve_constraints=[],
    )

    updated_itinerary = edit_trip_itinerary(edit_request)

    assert updated_itinerary.days[1].spots[0].name == "自由活动 / 弹性安排"
    assert "减少固定景点安排" in updated_itinerary.days[1].spots[0].description


def test_edit_trip_itinerary_can_apply_llm_day_edit(monkeypatch) -> None:
    """测试当 LLM 编辑草稿可用时，会优先重写目标日安排。"""

    class FakeDayEditDraft:
        theme = "更轻松的洱海慢游"
        spot_name = "双廊古镇"
        spot_description = "更适合慢节奏看海和看日落。"
        meal_name = "海景下午茶"
        meal_notes = "少辣，轻松休息。"
        daily_note = "下午再出发，去双廊慢慢看日落。"

    monkeypatch.setattr(
        trip_service,
        "generate_day_edit_draft",
        lambda request, target_day: FakeDayEditDraft(),
    )
    original_itinerary = generate_trip_itinerary(build_trip_request())

    edit_request = TripEditRequest(
        trip_id=original_itinerary.trip_id,
        current_itinerary=original_itinerary,
        user_instruction="第二天改得更轻松一点，不要安排太满",
        edit_scope="day_2",
        preserve_constraints=["保留预算结构"],
    )

    updated_itinerary = edit_trip_itinerary(edit_request)

    assert updated_itinerary.days[1].theme == "更轻松的洱海慢游"
    assert updated_itinerary.days[1].spots[0].name == "双廊古镇"
    assert updated_itinerary.days[1].meals[0].name == "海景下午茶"
    assert updated_itinerary.days[1].notes[-1] == "下午再出发，去双廊慢慢看日落。"

def test_generate_trip_itinerary_includes_local_guide_context() -> None:
    """测试生成结果已经开始包含本地攻略检索信息。"""
    itinerary = generate_trip_itinerary(build_trip_request())

    joined_notes = "\n".join(itinerary.source_notes)
    joined_spots = "\n".join(day.spots[0].name for day in itinerary.days if day.spots)

    assert len(itinerary.source_notes) >= 2
    assert "大理" in joined_notes
    assert (
        "大理古城" in joined_spots
        or "喜洲古镇" in joined_spots
        or "崇圣寺三塔" in joined_spots
        or "洱海生态廊道" in joined_spots
    )


def test_generate_trip_itinerary_uses_rag_ticket_prices_for_dali(monkeypatch) -> None:
    """测试门票优先使用大理本地攻略里的明确价格。"""

    draft = SimpleNamespace(
        summary="大理轻松慢游",
        tips=["洱海生态廊道骑行可租自行车，约30元/天。"],
        days=[
            SimpleNamespace(
                day_index=1,
                theme="古城慢逛",
                spot_name="大理古城",
                spot_description="适合傍晚散步。",
                meal_name="野生菌火锅",
                meal_notes="少辣。",
                daily_note="下午再出发。",
            ),
            SimpleNamespace(
                day_index=2,
                theme="洱海骑行",
                spot_name="洱海生态廊道",
                spot_description="适合骑行和看日落。",
                meal_name="喜洲粑粑",
                meal_notes="轻食。",
                daily_note="傍晚看日落。",
            ),
            SimpleNamespace(
                day_index=3,
                theme="三塔收尾",
                spot_name="崇圣寺三塔",
                spot_description="适合拍照。",
                meal_name="清淡简餐",
                meal_notes="少辣。",
                daily_note="晚些出发。",
            ),
        ],
    )
    rag_contexts = [
        "[来源: dali_guide.md | 标题: 2.1 大理古城]\n* **门票**：免费",
        (
            "[来源: dali_guide.md | 标题: 2.4 洱海生态廊道 (骑行)]\n"
            "* **门票**：免费 (自行车租赁约 30元/天)"
        ),
        "[来源: dali_guide.md | 标题: 2.2 崇圣寺三塔]\n* **门票**：75元/人",
    ]
    monkeypatch.setattr(trip_service, "collect_trip_context", lambda **kwargs: rag_contexts)
    monkeypatch.setattr(
        trip_service,
        "generate_planner_draft",
        lambda request, rag_contexts, day_count: draft,
    )

    itinerary = generate_trip_itinerary(build_trip_request())

    assert [day.spots[0].estimated_cost for day in itinerary.days] == [0.0, 0.0, 75.0]
    assert "门票参考本地攻略：免费" in itinerary.days[0].spots[0].description
    assert "自行车租赁约 30元/天" in itinerary.days[1].spots[0].description
    assert "门票参考本地攻略：75元/人" in itinerary.days[2].spots[0].description


def test_generate_trip_itinerary_uses_free_chengdu_ticket_and_filters_tip(
    monkeypatch,
) -> None:
    """测试成都免费景点不再被估价，并过滤跨目的地提示。"""
    request = build_trip_request().model_copy(update={"destination": "成都"})
    draft = SimpleNamespace(
        summary="成都轻松慢游",
        tips=["阴雨天路面湿滑，洱海边和古镇石板路建议穿防滑鞋。"],
        days=[
            SimpleNamespace(
                day_index=1,
                theme="古街慢游",
                spot_name="宽窄巷子",
                spot_description="适合傍晚散步。",
                meal_name="小吃",
                meal_notes="少辣。",
                daily_note="下午再出发。",
            ),
            SimpleNamespace(
                day_index=2,
                theme="熊猫基地",
                spot_name="大熊猫繁育研究基地",
                spot_description="适合轻松观赏。",
                meal_name="简餐",
                meal_notes="少辣。",
                daily_note="晚些入园。",
            ),
            SimpleNamespace(
                day_index=3,
                theme="人文收尾",
                spot_name="武侯祠",
                spot_description="红墙竹影适合拍照。",
                meal_name="锦里小吃",
                meal_notes="少辣。",
                daily_note="轻松收尾。",
            ),
        ],
    )
    rag_contexts = [
        "[来源: chengdu_guide.md | 标题: 2.2 宽窄巷子]\n* **门票**：免费",
        "[来源: chengdu_guide.md | 标题: 2.1 大熊猫繁育研究基地]\n* **门票**：55元/人",
        "[来源: chengdu_guide.md | 标题: 2.3 武侯祠]\n* **门票**：50元/人",
    ]
    monkeypatch.setattr(trip_service, "collect_trip_context", lambda **kwargs: rag_contexts)
    monkeypatch.setattr(
        trip_service,
        "generate_planner_draft",
        lambda request, rag_contexts, day_count: draft,
    )

    itinerary = generate_trip_itinerary(request)

    assert [day.spots[0].estimated_cost for day in itinerary.days] == [0.0, 55.0, 50.0]
    assert all("洱海" not in tip for tip in itinerary.tips)


def test_generate_trip_itinerary_calls_map_enrichment_for_spot_coordinates(
    monkeypatch,
) -> None:
    """测试生成链路会调用地图补全，从而为前端地图提供点位坐标。"""
    monkeypatch.setattr(trip_service, "collect_trip_context", lambda **kwargs: [])
    monkeypatch.setattr(
        trip_service,
        "generate_planner_draft",
        lambda request, rag_contexts, day_count: None,
    )

    captured: dict[str, object] = {}

    def fake_enrich(itinerary, city=None):
        captured["called"] = True
        captured["city"] = city
        first_spot = itinerary.days[0].spots[0]
        first_spot.latitude = 25.6065
        first_spot.longitude = 100.2676
        return itinerary

    monkeypatch.setattr(trip_service, "enrich_itinerary_with_map_data", fake_enrich)

    itinerary = trip_service.generate_trip_itinerary(build_trip_request())

    assert captured == {"called": True, "city": "大理"}
    assert itinerary.days[0].spots[0].latitude == 25.6065
    assert itinerary.days[0].spots[0].longitude == 100.2676
