# Destination Intelligence Agent

This package is reserved for a future destination-intelligence workflow that complements `trip_planner_agent`.

Goal: before generating or refining a trip plan, collect and synthesize current destination signals so the app can recommend the most suitable places, travel style, meals, and lodging for the user's timing and preferences.

```text
destination_intelligence_agent/
├── agent.py       # future public workflow orchestration and fallback boundary
├── llms/          # future model settings and provider-specific client factories
├── nodes/         # future steps: signal collection, sentiment synthesis, recommendation ranking
├── tools/         # future data-source tools: RAG, weather, map/local-life, web/social signals
├── utils/         # future parsing, normalization, scoring, and provider-response helpers
├── state/         # future Pydantic models exchanged by workflow steps
└── prompts/       # future prompt builders for public-opinion and travel-fit analysis
```

## Intended responsibilities

- Analyze target-destination public sentiment and travel conditions around the requested travel dates.
- Identify currently suitable attractions and neighborhoods, including reasons and cautions.
- Recommend travel styles such as relaxed walking, family-friendly routes, photography-focused trips, food tours, or bad-weather alternatives.
- Recommend meals and lodging areas that match budget, dietary preferences, pace, and recent local signals.
- Return structured output that `trip_service.py` or `trip_planner_agent` can consume later without making LLM availability mandatory.

## Draft workflow

1. Collect deterministic context from existing internal sources first: local guides, weather, AMap/local-life enrichment, and saved destination metadata.
2. Optionally collect time-sensitive public signals from approved web or social data sources.
3. Normalize signals into structured evidence with source, recency, sentiment, risk, and relevance.
4. Rank recommended attractions, travel modes, meals, and lodging areas for the specific trip request.
5. Return a compact `DestinationIntelligenceDraft` for downstream itinerary generation.

## Non-goals for this scaffold

- No runtime code is implemented yet.
- No external web/social scraping is wired yet.
- No API route or service integration is added yet.
