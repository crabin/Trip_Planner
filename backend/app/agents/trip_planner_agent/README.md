# Trip Planner Agent

The package is split by responsibility so model providers, prompts, parsing,
and domain state can evolve independently:

```text
trip_planner_agent/
├── agent.py       # public workflow orchestration and fallback boundary
├── llms/          # model settings and client factories
├── nodes/         # context collection and structured generation steps
├── tools/         # RAG query and deterministic arithmetic tools
├── utils/         # provider-response and JSON parsing helpers
├── state/         # Pydantic models exchanged by workflow steps
└── prompts/       # planning and single-day editing prompt builders
```

Import workflow functions from `app.agents.trip_planner_agent`. Focused code
may import its owning submodule directly. The former `app.agents.tools` paths
remain as compatibility aliases for scripts and downstream callers.
