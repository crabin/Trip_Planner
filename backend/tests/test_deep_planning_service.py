from pathlib import Path
import sys
from types import SimpleNamespace


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import TripRequest  # noqa: E402
import app.services.deep_planning_service as deep_service  # noqa: E402
from app.services.deep_planning_service import (  # noqa: E402
    build_deep_planning_query,
    run_deep_planning_job,
)


def test_build_deep_planning_query_integrates_every_planning_field() -> None:
    query = build_deep_planning_query(
        TripRequest(
            destination="京都",
            start_date="2026-10-02",
            end_date="2026-10-06",
            travelers=2,
            budget=200000,
            preferences=["寺社", "美食"],
            pace="轻松",
            dietary_preferences=["不吃香菜"],
            hotel_level="高档型",
            special_notes="从东京出发，避免过早起床",
        )
    )

    for expected in (
        "目的地：京都",
        "2026-10-02 至 2026-10-06",
        "同行人数：2 人",
        "总预算：200000",
        "寺社、美食",
        "节奏偏好：轻松",
        "住宿偏好：高档型",
        "饮食偏好：不吃香菜",
        "从东京出发，避免过早起床",
    ):
        assert expected in query


def test_background_job_persists_markdown_sources_and_progress(monkeypatch) -> None:
    updates: list[tuple[int, str]] = []
    completed: list[object] = []
    failures: list[str] = []

    source = SimpleNamespace(
        query="京都交通",
        title="京都市交通局",
        url="https://example.com/kyoto",
        content="交通信息摘要",
        score=0.96,
        published_date="2026-06-20",
    )

    class FakeAgent:
        def __init__(self, config=None) -> None:
            assert config is not None
            assert config.OUTPUT_DIR.endswith("destination_intelligence_streamlit_reports")
            self.state = SimpleNamespace(
                paragraphs=[
                    SimpleNamespace(
                        title="交通与住宿",
                        research=SimpleNamespace(search_history=[source]),
                    )
                ]
            )

        def research(self, query, save_report, progress_callback):
            assert "目的地：京都" in query
            assert save_report is True
            progress_callback(45, "已完成 2/5 个研究章节")
            return "# 京都深度旅行攻略\n\n完整内容"

    monkeypatch.setattr(
        "app.agents.destination_intelligence_agent.DestinationIntelligenceAgent",
        FakeAgent,
    )
    monkeypatch.setattr(
        deep_service,
        "update_deep_plan_progress",
        lambda trip_id, progress, message: updates.append((progress, message)),
    )
    monkeypatch.setattr(
        deep_service,
        "complete_deep_plan",
        lambda trip_id, document: completed.append(document),
    )
    monkeypatch.setattr(
        deep_service,
        "fail_deep_plan",
        lambda trip_id, error: failures.append(error),
    )

    run_deep_planning_job(
        "deep_test",
        TripRequest(
            destination="京都",
            start_date="2026-10-02",
            end_date="2026-10-06",
            travelers=2,
            budget=200000,
        ),
    )

    assert updates == [(45, "已完成 2/5 个研究章节")]
    assert failures == []
    assert len(completed) == 1
    assert completed[0].markdown.startswith("# 京都")
    assert completed[0].sources[0].title == "京都市交通局"
