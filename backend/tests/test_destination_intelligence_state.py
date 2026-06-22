import json

import pytest

from app.agents.destination_intelligence_agent.state import Research, State


def test_research_adds_all_search_results() -> None:
    research = Research()

    research.add_search_results(
        "北京两日游天气",
        [
            {
                "title": "北京天气",
                "url": "https://example.com/weather",
                "content": "晴到多云",
                "score": 0.9,
            },
            {
                "title": "北京出行建议",
                "url": "https://example.com/travel",
                "content": "注意防晒",
                "score": 0.8,
            },
        ],
    )

    assert research.get_search_count() == 2
    assert [search.query for search in research.search_history] == [
        "北京两日游天气",
        "北京两日游天气",
    ]
    assert research.search_history[0].title == "北京天气"


def test_research_increments_reflection() -> None:
    research = Research()

    research.increment_reflection()

    assert research.reflection_iteration == 1


def test_state_json_file_round_trip(tmp_path) -> None:
    state = State(query="2026年厦门旅行", report_title="厦门旅行攻略")
    paragraph_index = state.add_paragraph("逐日行程", "规划每天的时间地点链")
    state.paragraphs[paragraph_index].research.latest_summary = "D1 抵达厦门"
    state.paragraphs[paragraph_index].research.mark_completed()
    state.final_report = "# 厦门旅行攻略"
    state.mark_completed()
    state_path = tmp_path / "state.json"

    state.save_to_file(state_path)
    restored = State.load_from_file(state_path)

    assert json.loads(state.to_json()) == state.to_dict()
    assert restored.to_dict() == state.to_dict()


def test_state_save_does_not_destroy_existing_file_when_serialization_fails(
    tmp_path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"query":"previous"}', encoding="utf-8")
    state = State(query="new")

    def fail_serialization() -> str:
        raise TypeError("cannot serialize")

    monkeypatch.setattr(state, "to_json", fail_serialization, raising=False)

    with pytest.raises(TypeError, match="cannot serialize"):
        state.save_to_file(state_path)

    assert state_path.read_text(encoding="utf-8") == '{"query":"previous"}'
