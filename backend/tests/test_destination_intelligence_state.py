from app.agents.destination_intelligence_agent.state import Research


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
