from app.agents.destination_intelligence_agent.utils.config import Settings


def test_settings_repr_redacts_api_keys() -> None:
    settings = Settings(
        DESTINATION_INTELLIGENCE_AGENT_API_KEY="llm-secret-value",
        DESTINATION_INTELLIGENCE_AGENT_MODEL_NAME="test-model",
        TAVILY_API_KEY="search-secret-value",
        UNRELATED_SECRET="other-secret-value",
    )

    rendered = repr(settings)

    assert "llm-secret-value" not in rendered
    assert "search-secret-value" not in rendered
    assert "other-secret-value" not in rendered
    assert "test-model" in rendered
