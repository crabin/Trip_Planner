from datetime import date, timedelta
import json
from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient
import pytest


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.main import app  # noqa: E402
from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    DayPlan,
    DeepPlanDocument,
    Itinerary,
    TripRequest,
)
import app.services.report_catalog_service as report_service  # noqa: E402
import app.services.report_itinerary_service as report_itinerary_service  # noqa: E402
from app.services.storage_service import (  # noqa: E402
    complete_deep_plan,
    create_deep_plan,
    delete_trip_by_trip_id,
    get_itinerary_by_trip_id,
    list_saved_itineraries,
    save_itinerary,
)


client = TestClient(app)


@pytest.fixture
def report_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(report_service, "REPORT_DIR", tmp_path)
    report_service._load_catalog.cache_clear()
    monkeypatch.setattr(
        report_itinerary_service,
        "_maybe_enrich_itinerary_with_map_data",
        lambda itinerary, city=None, request_budget=None: itinerary,
    )
    yield tmp_path
    report_service._load_catalog.cache_clear()


def _write_report(
    report_dir: Path,
    stem: str,
    markdown: str,
    state: dict | None = None,
) -> tuple[Path, Path]:
    markdown_path = report_dir / f"travel_guide_{stem}.md"
    state_path = report_dir / f"state_{stem}.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    if state is None:
        state_path.write_text("", encoding="utf-8")
    else:
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return markdown_path, state_path


def _complete_extracted_report(
    start: date,
    plans: list[dict[str, str]],
    *,
    overview: str = "结构化 Report 概览",
    total_budget: float = 0.0,
):
    days = []
    for offset, plan in enumerate(plans):
        current_date = start + timedelta(days=offset)
        spot_name = plan.get("spot", "")
        meal_name = plan.get("meal", "")
        days.append(
            report_itinerary_service._ExtractedDay(
                day_index=offset + 1,
                date=current_date.isoformat(),
                theme=plan["theme"],
                full_day_text=plan.get("text", plan["theme"]),
                spots=(
                    [
                        report_itinerary_service._ExtractedSpot(
                            name=spot_name,
                            map_query=f"测试城市 {spot_name}",
                        )
                    ]
                    if spot_name
                    else []
                ),
                meals=(
                    [
                        report_itinerary_service._ExtractedMeal(
                            name=meal_name,
                            meal_type="晚餐",
                            map_query=f"测试城市 {meal_name}",
                        )
                    ]
                    if meal_name
                    else []
                ),
                hotel_name=plan.get("hotel", ""),
                hotel_query=plan.get("hotel", ""),
                source_chunk_ids=[f"test-{offset + 1}"],
            )
        )
    return report_itinerary_service._ExtractedReport(
        overview=overview,
        start_date=start.isoformat(),
        end_date=(start + timedelta(days=len(plans) - 1)).isoformat(),
        total_days=len(plans),
        total_budget=total_budget,
        tips=["复核交通与预约规则。"],
        days=days,
    )


def test_catalog_loads_valid_sources_and_tolerates_corrupt_state(report_dir) -> None:
    _write_report(
        report_dir,
        "2026-7-02至7-06从长沙去汕头_20260622_210806_141870",
        "# 汕头 2026-07-02 至 2026-07-06 旅行攻略\n\n完整攻略",
        {
            "query": "2026-7-02至7-06，从长沙去汕头，2位成人",
            "report_title": "汕头深度旅行攻略",
            "created_at": "2026-06-22T20:35:58",
            "updated_at": "2026-06-22T21:08:06",
            "paragraphs": [
                {
                    "title": "交通与住宿",
                    "research": {
                        "search_history": [
                            {
                                "query": "汕头交通",
                                "title": "交通来源",
                                "url": "https://example.com/shantou",
                                "content": "来源摘要",
                                "score": 0.95,
                                "published_date": "2026-06-20",
                            }
                        ]
                    },
                }
            ],
        },
    )
    _write_report(
        report_dir,
        "2026-7-02至7-06从长沙去厦门_20260622_190804",
        "# 厦门 2026-07-02 至 2026-07-06 旅行攻略\n\nMarkdown fallback",
    )

    artifacts = report_service.list_report_artifacts()

    assert len(artifacts) == 2
    shantou = next(item for item in artifacts if item.destination == "汕头")
    xiamen = next(item for item in artifacts if item.destination == "厦门")
    assert shantou.dates == ("2026-07-02", "2026-07-06")
    assert shantou.document.sources[0].section_title == "交通与住宿"
    assert xiamen.document.sources == []
    assert "Markdown fallback" in xiamen.document.markdown


def test_quick_trip_and_matching_report_merge_into_one_three_action_item(report_dir) -> None:
    _write_report(
        report_dir,
        "2026-7-02至7-06从长沙去汕头_20260622_210806_141870",
        "# 汕头 2026-07-02 至 2026-07-06 旅行攻略\n\n完整攻略",
        {"query": "2026-7-02至7-06，从长沙去汕头，2位成人"},
    )
    trip_id = f"trip_report_match_{uuid.uuid4().hex}"
    itinerary = Itinerary(
        trip_id=trip_id,
        destination="汕头",
        summary="汕头快速规划",
        days=[
            DayPlan(day_index=1, date=date(2026, 7, 2)),
            DayPlan(day_index=2, date=date(2026, 7, 6)),
        ],
        budget_breakdown=BudgetBreakdown(),
    )
    save_itinerary(itinerary)

    try:
        items = list_saved_itineraries().items
        matched = next(item for item in items if item.trip_id == trip_id)
        assert matched.has_detail is True
        assert matched.has_itinerary is True
        assert matched.has_report is True
        assert matched.report_id is not None
        assert matched.is_report_only is False
        assert not any(
            item.is_report_only and item.report_id == matched.report_id for item in items
        )
    finally:
        delete_trip_by_trip_id(trip_id)


def test_report_json_markdown_and_delete_endpoints(report_dir) -> None:
    markdown_path, state_path = _write_report(
        report_dir,
        "从长沙去北京_20260622_221046_628883",
        "# 北京旅行攻略\n\nReport body",
        {"query": "从长沙去北京，2位成人", "report_title": "北京深度旅行攻略"},
    )
    artifact = report_service.list_report_artifacts()[0]

    detail_response = client.get(f"/trip/reports/{artifact.report_id}")
    markdown_response = client.get(f"/trip/reports/{artifact.report_id}/markdown")

    assert detail_response.status_code == 200
    assert detail_response.json()["deep_plan"]["markdown"].startswith("# 北京")
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert "Report body" in markdown_response.text

    delete_response = client.delete(f"/trip/{artifact.report_id}")
    assert delete_response.status_code == 200
    assert not markdown_path.exists()
    assert not state_path.exists()


def test_deleting_quick_trip_preserves_matched_report_artifact(report_dir) -> None:
    markdown_path, state_path = _write_report(
        report_dir,
        "2026-7-02至7-06从长沙去汕头_20260622_210806_141870",
        "# 汕头 2026-07-02 至 2026-07-06 旅行攻略\n\n完整攻略",
        {"query": "2026-7-02至7-06，从长沙去汕头，2位成人"},
    )
    artifact = report_service.list_report_artifacts()[0]
    trip_id = f"trip_report_delete_{uuid.uuid4().hex}"
    save_itinerary(
        Itinerary(
            trip_id=trip_id,
            destination="汕头",
            summary="汕头快速规划",
            days=[
                DayPlan(day_index=1, date=date(2026, 7, 2)),
                DayPlan(day_index=2, date=date(2026, 7, 6)),
            ],
            budget_breakdown=BudgetBreakdown(),
        )
    )

    response = client.delete(f"/trip/{trip_id}")

    assert response.status_code == 200
    assert markdown_path.exists()
    assert state_path.exists()
    assert report_service.get_report_artifact(artifact.report_id) is not None


def test_report_itinerary_endpoint_generates_and_caches_result_page_data(report_dir, monkeypatch) -> None:
    _write_report(
        report_dir,
            "2026-7-02至7-03从长沙去厦门_20260622_190804",
        "\n".join(
            [
                    "# 厦门 2026-07-02 至 2026-07-03 深度旅行攻略",
                "## 第1天 鼓浪屿与中山路",
                "- 景点：鼓浪屿",
                "- 餐饮：八市海鲜小吃",
                "- 酒店：厦门海景舒适酒店",
                "## 第2天 南普陀与环岛路",
                "- 景点：南普陀寺",
                "- 晚餐：沙茶面老店",
            ]
        ),
            {"query": "2026-7-02至7-03，从长沙去厦门，2位成人", "report_title": "厦门深度旅行攻略"},
        )
    artifact = report_service.list_report_artifacts()[0]
    calls = {"count": 0}

    def fake_extract(**_kwargs):
        calls["count"] += 1
        return _complete_extracted_report(
            date(2026, 7, 2),
            [
                {"theme": "鼓浪屿与中山路", "spot": "鼓浪屿", "meal": "八市海鲜小吃", "hotel": "厦门海景舒适酒店"},
                {"theme": "南普陀与环岛路", "spot": "南普陀寺", "meal": "沙茶面老店"},
            ],
        )

    monkeypatch.setattr(report_itinerary_service, "_extract_report_with_llm", fake_extract)

    first_response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")
    second_response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    itinerary = first_response.json()
    assert itinerary["trip_id"] == second_response.json()["trip_id"]
    assert itinerary["destination"] == "厦门"
    assert itinerary["days"][0]["spots"][0]["name"] == "鼓浪屿"
    assert itinerary["days"][0]["meals"][0]["name"] == "八市海鲜小吃"
    assert itinerary["days"][0]["hotel"]["name"] == "厦门海景舒适酒店"
    assert itinerary["conversion_meta"]["version"] == "report-itinerary-llm-v2"
    assert calls["count"] == 1
    assert get_itinerary_by_trip_id(itinerary["trip_id"]) is not None
    assert itinerary["trip_id"] not in {
        item.trip_id for item in list_saved_itineraries().items
    }

    delete_trip_by_trip_id(itinerary["trip_id"])


def test_report_itinerary_endpoint_does_not_reuse_matching_quick_trip(report_dir, monkeypatch) -> None:
    _write_report(
        report_dir,
            "2026-7-02从长沙去汕头_20260622_210806_141870",
            "# 汕头 2026-07-02 旅行攻略\n\n- 景点：小公园开埠区",
            {"query": "2026-7-02，从长沙去汕头，2位成人"},
    )
    artifact = report_service.list_report_artifacts()[0]
    trip_id = f"trip_report_reuse_{uuid.uuid4().hex}"
    itinerary = Itinerary(
        trip_id=trip_id,
        destination="汕头",
        summary="已存在的汕头结果页",
        days=[
            DayPlan(day_index=1, date=date(2026, 7, 2)),
            DayPlan(day_index=2, date=date(2026, 7, 6)),
        ],
        budget_breakdown=BudgetBreakdown(),
    )
    save_itinerary(itinerary)
    monkeypatch.setattr(
        report_itinerary_service,
        "_extract_report_with_llm",
        lambda **_kwargs: _complete_extracted_report(
            date(2026, 7, 2),
            [{"theme": "汕头老城", "spot": "小公园开埠区"}],
        ),
    )

    try:
        response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")

        assert response.status_code == 200
        assert response.json()["trip_id"] != trip_id
        assert response.json()["days"][0]["spots"][0]["name"] == "小公园开埠区"
    finally:
        delete_trip_by_trip_id(trip_id)


def test_report_itinerary_returns_503_when_llm_factory_fails(report_dir, monkeypatch) -> None:
    _write_report(
        report_dir,
        "llm_factory_failure_20260622_221046",
        "\n".join(
            [
                "# 大理 2026-04-10 至 2026-04-12 深度旅行攻略",
                "## 第1天 大理古城",
                "- 景点：大理古城",
                "- 餐饮：白族风味餐厅",
            ]
        ),
        {"query": "从长沙去大理", "report_title": "大理深度旅行攻略"},
    )
    artifact = report_service.list_report_artifacts()[0]

    def broken_llm_factory():
        raise RuntimeError("bad llm config")

    monkeypatch.setattr(report_itinerary_service, "build_chat_llm", broken_llm_factory)

    response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "report_conversion_unavailable"
    cache_id = report_itinerary_service._cache_trip_id("report_itinerary", artifact.report_id)
    assert get_itinerary_by_trip_id(cache_id) is None


def test_report_itinerary_returns_422_and_does_not_save_partial_result(report_dir, monkeypatch) -> None:
    _write_report(
        report_dir,
        "strict_partial_20260622_221046",
        "# 洛阳 2026-06-25 至 2026-06-26 旅行攻略\n\n## 每日行程",
        {"query": "2026-06-25 至 2026-06-26 去洛阳"},
    )
    artifact = report_service.list_report_artifacts()[0]
    monkeypatch.setattr(
        report_itinerary_service,
        "_extract_report_with_llm",
        lambda **_kwargs: _complete_extracted_report(
            date(2026, 6, 25),
            [{"theme": "只有第一天", "spot": "应天门"}],
        ),
    )

    response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "report_conversion_incomplete"
    cache_id = report_itinerary_service._cache_trip_id("report_itinerary", artifact.report_id)
    assert get_itinerary_by_trip_id(cache_id) is None


def test_report_itinerary_continues_when_structured_json_save_fails(
    report_dir,
    monkeypatch,
) -> None:
    _write_report(
        report_dir,
        "structured_json_write_failure_20260622_221046",
        "# 北京 2026-06-29 一日旅行攻略\n\n## 每日行程\n### 2026-06-29（周一）D1｜首日",
        {"query": "从长沙去北京", "report_title": "北京深度旅行攻略"},
    )
    artifact = report_service.list_report_artifacts()[0]
    monkeypatch.setattr(
        report_itinerary_service,
        "_save_extracted_report_json",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(
        report_itinerary_service,
        "_extract_report_with_llm",
        lambda **_kwargs: report_itinerary_service._ExtractedReport(
            overview="一屏概览：北京两日游",
            days=[
                report_itinerary_service._ExtractedDay(
                    day_index=1,
                    date="2026-06-29",
                    theme="首日",
                    full_day_text="王府井商圈",
                    spots=[
                        report_itinerary_service._ExtractedSpot(
                            name="王府井",
                            map_query="北京 王府井",
                        )
                    ],
                )
            ],
        ),
    )

    response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")

    assert response.status_code == 200
    itinerary = response.json()
    assert itinerary["summary"] == "一屏概览：北京两日游"
    assert itinerary["days"][0]["spots"][0]["name"] == "王府井"

    delete_trip_by_trip_id(itinerary["trip_id"])


def test_beijing_report_itinerary_uses_overview_days_and_never_reuses_budget_as_item_cost(
    report_dir,
    monkeypatch,
) -> None:
    _write_report(
        report_dir,
        "下周一到周周六周天回长沙从长沙去北京2位成人想看天安门要去长_20260622_221046_628883",
        "\n".join(
            [
                "# 北京 2026-06-29 至 2026-06-30（2天1晚）旅行攻略",
                "> 一屏概览：",
                "> **日期**：2026-06-29（周一）出发，2026-06-30（周二）返长沙，共 **2天1晚**",
                "> **预算口径**：默认按 **2人总预算约10000元，含往返大交通+住宿+市内交通+门票+餐饮** 做控制",
                "> **确认方法**：12306、天安门广场预约平台、故宫订票官网",
                "---",
                "## 每日行程",
                "### 2026-06-29（周一）D1｜长沙出发，北京入住 + 前门/王府井轻量适应",
                "- **时间—地点链**",
                "  - 长沙 → 北京（飞机或高铁，待确认班次）",
                "- **景点/体验**",
                "  - 王府井/东单商圈，1–2小时，方便吃饭与补给",
                "- **午晚餐或商圈**",
                "  - 若住东单/王府井：优先王府井、灯市口附近",
                "- **当日住宿与回程**",
                "  - 住宿：北京第1晚",
                "### 2026-06-30（周二）D2｜中轴线核心日：天安门区域 + 故宫 + 景山 + 前门晚餐",
                "- **景点/体验**",
                "  1. **天安门广场/天安门区域**",
                "     - 建议时长：1–2小时",
                "  2. **故宫博物院**",
                "     - 实名预约，不售当日票",
                "  3. **景山公园**",
                "     - 开放/票务：待确认，以官方为准",
                "- **午晚餐或商圈**",
                "  - 晚餐：**前门/大栅栏** 优先，适合京味老字号",
            ]
        ),
        {
            "query": "2026-06-29 至 2026-06-30，从长沙去北京，2位成人，预算约10000元",
            "report_title": "目的地旅行攻略｜长沙去北京",
        },
    )
    artifact = report_service.list_report_artifacts()[0]
    monkeypatch.setattr(
        report_itinerary_service,
        "_extract_report_with_llm",
        lambda **_kwargs: report_itinerary_service._ExtractedReport(
            overview=(
                "一屏概览：\n"
                "日期：2026-06-29（周一）出发，2026-06-30（周二）返长沙，共 2天1晚\n"
                "预算口径：默认按 2人总预算约10000元，含往返大交通+住宿+市内交通+门票+餐饮 做控制"
            ),
            total_budget=10000,
            tips=["复核天安门、故宫、长城和酒店规则。"],
            days=[
                report_itinerary_service._ExtractedDay(
                    day_index=1,
                    date="2026-06-29",
                    theme="长沙出发，北京入住 + 前门/王府井轻量适应",
                    full_day_text="时间—地点链\n长沙 → 北京\n景点/体验\n王府井/东单商圈，1–2小时",
                    spots=[
                        report_itinerary_service._ExtractedSpot(
                            name="王府井",
                            map_query="北京 王府井",
                            description="首日轻量商圈活动",
                        )
                    ],
                    meals=[
                        report_itinerary_service._ExtractedMeal(
                            name="王府井附近京味菜",
                            meal_type="晚餐",
                            map_query="北京 王府井 京味菜",
                            notes="首日晚餐不要排太远。",
                        )
                    ],
                    hotel_name="北京东城核心区酒店",
                    hotel_query="北京 东城 前门 崇文门 王府井 酒店",
                    transport_note="地铁为主，打车补位",
                ),
                report_itinerary_service._ExtractedDay(
                    day_index=2,
                    date="2026-06-30",
                    theme="中轴线核心日：天安门区域 + 故宫 + 景山 + 前门晚餐",
                    full_day_text="景点/体验\n天安门广场\n故宫博物院\n景山公园",
                    spots=[
                        report_itinerary_service._ExtractedSpot(
                            name="天安门广场",
                            map_query="北京 天安门广场",
                        ),
                        report_itinerary_service._ExtractedSpot(
                            name="故宫博物院",
                            map_query="北京 故宫博物院",
                        ),
                        report_itinerary_service._ExtractedSpot(
                            name="景山公园",
                            map_query="北京 景山公园",
                        ),
                    ],
                    meals=[],
                    hotel_name="北京东城核心区酒店",
                    hotel_query="北京 东城 前门 崇文门 王府井 酒店",
                    transport_note="步行与地铁衔接",
                ),
            ],
        ),
    )

    response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")

    assert response.status_code == 200
    itinerary = response.json()
    assert itinerary["summary"].startswith("一屏概览")
    assert "预算口径" in itinerary["summary"]
    assert itinerary["estimated_budget"] == 10000
    assert itinerary["budget_breakdown"]["total"] == 10000
    assert itinerary["days"][0]["spots"][0]["name"] == "王府井"
    assert itinerary["days"][0]["spots"][0]["map_query"] == "北京 王府井"
    assert itinerary["days"][0]["spots"][0]["estimated_cost"] is None
    assert itinerary["days"][1]["spots"][0]["name"] == "天安门广场"
    assert itinerary["days"][1]["spots"][1]["name"] == "故宫博物院"
    assert itinerary["days"][1]["spots"][2]["name"] == "景山公园"
    all_text = json.dumps(itinerary, ensure_ascii=False)
    assert "2位成人" not in [spot["name"] for day in itinerary["days"] for spot in day["spots"]]
    assert "开放" not in [spot["name"] for day in itinerary["days"] for spot in day["spots"]]
    assert "根据深度规划 Report 提取" not in all_text
    assert "可结合地图评分再筛选" not in all_text
    assert itinerary["conversion_meta"]["version"] == "report-itinerary-llm-v2"

    delete_trip_by_trip_id(itinerary["trip_id"])


def test_report_itinerary_force_rebuild_skips_cached_conversion(report_dir, monkeypatch) -> None:
    _write_report(
        report_dir,
        "force_refresh_beijing_20260622_221046",
        "# 北京 2026-06-29 一日旅行攻略\n\n## 每日行程\n### 2026-06-29（周一）D1｜首日",
        {"query": "从长沙去北京，预算约10000元", "report_title": "北京深度旅行攻略"},
    )
    artifact = report_service.list_report_artifacts()[0]
    call_count = {"value": 0}

    def fake_extract(**_kwargs):
        call_count["value"] += 1
        return report_itinerary_service._ExtractedReport(
            overview=f"一屏概览：第 {call_count['value']} 次转换",
            total_budget=10000,
            days=[
                report_itinerary_service._ExtractedDay(
                    day_index=1,
                    date="2026-06-29",
                    theme="首日",
                    full_day_text="首日完整行程",
                    spots=[
                        report_itinerary_service._ExtractedSpot(
                            name=f"王府井{call_count['value']}",
                            map_query="北京 王府井",
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr(report_itinerary_service, "_extract_report_with_llm", fake_extract)

    first_response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")
    cached_response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")
    forced_response = client.get(f"/trip/reports/{artifact.report_id}/itinerary?force=true")

    assert first_response.status_code == 200
    assert cached_response.status_code == 200
    assert forced_response.status_code == 200
    assert call_count["value"] == 2
    assert cached_response.json()["summary"] == first_response.json()["summary"]
    assert forced_response.json()["summary"] == "一屏概览：第 2 次转换"
    assert forced_response.json()["days"][0]["spots"][0]["name"] == "王府井2"

    delete_trip_by_trip_id(forced_response.json()["trip_id"])


def test_report_itinerary_persists_structured_json_and_reuses_it_after_db_cache_deleted(
    report_dir,
    monkeypatch,
) -> None:
    _write_report(
        report_dir,
        "structured_json_reuse_20260622_221046",
        "\n".join(
            [
                "# 北京 2026-06-29 至 2026-06-30 旅行攻略",
                "> 一屏概览：",
                "> **预算口径**：2人总预算约10000元",
                "## 每日行程",
                "### 2026-06-29（周一）D1｜首日王府井",
                "- **景点/体验**",
                "  - 王府井商圈",
            ]
        ),
        {"query": "从长沙去北京", "report_title": "北京深度旅行攻略"},
    )
    artifact = report_service.list_report_artifacts()[0]
    call_count = {"value": 0}

    def fake_extract(*, markdown, source_id, cache_prefix, force_rebuild=False, **_kwargs):
        fingerprint = report_itinerary_service._source_sha256(markdown)
        if not force_rebuild:
            cached = report_itinerary_service._load_extracted_report_json(
                cache_prefix,
                source_id,
                source_sha256=fingerprint,
            )
            if cached is not None:
                return cached
        call_count["value"] += 1
        extracted = _complete_extracted_report(
            date(2026, 6, 29),
            [
                {"theme": "首日王府井", "spot": "王府井"},
                {"theme": "中轴线", "spot": "故宫博物院"},
            ],
            overview="一屏概览：\n预算口径：2人总预算约10000元",
            total_budget=10000,
        )
        report_itinerary_service._save_extracted_report_json(
            cache_prefix=cache_prefix,
            source_id=source_id,
            source_sha256=fingerprint,
            extracted=extracted,
            section_count=2,
            completed_section_count=2,
            model="test-model",
        )
        return extracted

    monkeypatch.setattr(report_itinerary_service, "_extract_report_with_llm", fake_extract)

    first_response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")
    assert first_response.status_code == 200
    first_itinerary = first_response.json()
    assert first_itinerary["days"][0]["spots"][0]["name"] == "王府井"
    json_path = Path(
        report_itinerary_service._extracted_report_json_path(
            "report_itinerary",
            artifact.report_id,
        )
    )
    assert json_path.is_file()
    first_call_count = call_count["value"]
    assert first_call_count > 0

    delete_trip_by_trip_id(first_itinerary["trip_id"])
    second_response = client.get(f"/trip/reports/{artifact.report_id}/itinerary")

    assert second_response.status_code == 200
    assert second_response.json()["days"][0]["spots"][0]["name"] == "王府井"
    assert call_count["value"] == first_call_count

    delete_trip_by_trip_id(second_response.json()["trip_id"])


def test_completed_deep_plan_can_be_converted_to_result_page_itinerary(report_dir, monkeypatch) -> None:
    item = create_deep_plan(
        TripRequest(
            destination="大理",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=2,
            budget=3200,
            preferences=["自然风景"],
            dietary_preferences=[],
        )
    )
    monkeypatch.setattr(
        report_itinerary_service,
        "_extract_report_with_llm",
        lambda **_kwargs: _complete_extracted_report(
            date(2026, 4, 10),
            [
                {"theme": "大理古城", "spot": "大理古城"},
                {"theme": "洱海慢游", "spot": "洱海"},
                {"theme": "返程", "spot": ""},
            ],
        ),
    )
    try:
        complete_deep_plan(
            item.trip_id,
            DeepPlanDocument(
                markdown="# 大理深度旅行攻略\n\n## 第1天 大理古城\n- 景点：大理古城\n- 餐饮：白族风味餐厅",
                sources=[],
            ),
        )

        response = client.get(f"/trip/{item.trip_id}/deep-itinerary")

        assert response.status_code == 200
        assert response.json()["destination"] == "大理"
        assert response.json()["days"][0]["spots"][0]["name"] == "大理古城"
        delete_trip_by_trip_id(response.json()["trip_id"])
    finally:
        detail = get_itinerary_by_trip_id(item.trip_id)
        if detail is not None:
            delete_trip_by_trip_id(item.trip_id)
