# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Trip Planner is a full-stack travel itinerary app for Chinese travel scenarios.

- `backend/`: FastAPI service that generates/edit itineraries, enriches them with RAG, weather, and map data, persists trips to SQLite, and exports Markdown/PDF.
- `frontend/`: Vue 3 + TypeScript + Vite SPA for trip creation, result display, history, map, weather, editing, and export.

The backend is the system of record for itinerary structure. The frontend mostly mirrors backend schema types and calls typed API wrappers in `frontend/src/services/api.ts`.

## Common commands

### Backend setup and run

```bash
cd backend
uv sync
cp .env.example .env
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

Notes:
- The real ASGI app is `backend/app/api/main.py`.
- `backend/main.py` is only a placeholder stub and is not the server entrypoint.
- If you are not using `uv`, `pip install -r requirements.txt` also works.

### Frontend setup and run

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Frontend build

```bash
cd frontend
npm run build
npm run preview
```

`npm run build` runs `vue-tsc --noEmit` before the Vite build.

### Backend tests

```bash
cd backend
pytest
pytest -q
pytest --cov=app --cov-report=term-missing
```

Run a single test file:

```bash
cd backend
pytest tests/test_rag_retriever.py -q
```

Run a single test:

```bash
cd backend
pytest tests/test_services_trip.py -k budget -q
```

### Backend lint / format

```bash
cd backend
ruff check app/
ruff format app/
```

### RAG data and debugging scripts

Initialize or rebuild the travel guide index:

```bash
cd backend
python scripts/ingest_data.py
```

Useful investigation scripts:

```bash
cd backend
python scripts/debug_rag_retrieval.py
python scripts/evaluate_rag_retrieval.py
python scripts/test_map_service.py
python scripts/test_trip_service_real.py
python scripts/test_trip_planner_agent_real.py
```

## Environment configuration

### Backend

`backend/.env.example` defines the real knobs used by the app:

- LLM: `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`
- RAG/vector store: `CHROMA_DB_DIR`, `CHROMA_COLLECTION_NAME`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`
- Cache: `REDIS_ENABLED`, `REDIS_URL`, TTL settings
- AMap: `AMAP_API_KEY`, `ENABLE_AMAP_ENRICHMENT`

Important defaults:
- `REDIS_ENABLED=false`: the app is expected to run without Redis.
- `ENABLE_AMAP_ENRICHMENT=false`: map enrichment is optional.

### Frontend

`frontend/.env.example` uses:

- `VITE_API_BASE_URL`
- `VITE_AMAP_JS_KEY`

If the browser is running on your local machine but the app is hosted remotely, do not point `VITE_API_BASE_URL` at the server's internal `127.0.0.1`.

## High-level architecture

### Backend request flow

Main entrypoint: `backend/app/api/main.py`

Routers:
- `backend/app/api/routes/trip.py`
- `backend/app/api/routes/export.py`
- `backend/app/api/routes/weather.py`

The main trip flow is:

1. `POST /trip/generate` or `POST /trip/edit` lands in the trip router.
2. The router delegates to `backend/app/services/trip_service.py`.
3. `trip_service.py` gathers destination context via `backend/app/agents/tools/rag_tool.py`.
4. The RAG tool calls `backend/app/rag/retriever.py`.
5. The retriever calls `backend/app/rag/vector_db.py` for search.
6. The planner/edit agent in `backend/app/agents/trip_planner_agent.py` tries to get structured JSON from the LLM.
7. `trip_service.py` builds or updates the final `Itinerary`, recalculates budget, and optionally enriches map data.

### Backend layering

- `backend/app/models/schemas.py`: Pydantic request/response/domain models. These define the itinerary shape used across API, service logic, and frontend TS types.
- `backend/app/models/db_models.py`: SQLAlchemy persistence models.
- `backend/app/services/trip_service.py`: orchestration layer; this is the core business logic file.
- `backend/app/services/storage_service.py`: SQLite CRUD for saved trips.
- `backend/app/services/export_service.py`: renders itinerary data into Markdown and PDF.
- `backend/app/services/weather_service.py`: external weather lookup.
- `backend/app/services/map_service.py`: AMap enrichment for POIs, routes, coordinates, and related details.
- `backend/app/services/cache_service.py`: Redis wrapper with graceful fallback when Redis is disabled/unavailable.

### RAG design

RAG uses local Markdown travel guides under `backend/data/`.

`backend/app/rag/vector_db.py` is more than a thin vector-store wrapper:
- it chunks Markdown guides by headings,
- maintains a persistent Chroma store,
- persists a local JSON embedding index,
- and falls back to keyword search when vector search is unavailable.

`backend/app/rag/retriever.py` adds travel-specific behavior on top of raw retrieval:
- destination-aware filtering to avoid cross-city leakage,
- lightweight reranking,
- Redis caching for retrieved context.

When changing retrieval quality, inspect both files together; ranking behavior is split across them.

### LLM behavior is optional, not mandatory

`backend/app/agents/trip_planner_agent.py` attempts structured generation/editing through LangChain + an OpenAI-compatible API.

`backend/app/services/trip_service.py` is designed to keep the product working even when LLM calls fail:
- generation can fall back to rule-based itinerary assembly,
- map enrichment is wrapped as optional,
- cache and Redis failures degrade rather than stop the request.

Do not assume an API key is always present when changing the backend flow.

### Persistence and generated artifacts

Backend runtime data lives under `backend/db/`:
- `app.db`: SQLite trip storage
- `chroma_db/`: Chroma persistent store
- `guide_embeddings.json`: local embedding/index artifact

These are generated/runtime artifacts, not the source of truth for application logic.

## Frontend structure

Main frontend entrypoints:
- `frontend/src/main.ts`
- `frontend/src/App.vue`

The app does not use `vue-router`. `frontend/src/App.vue` switches between `home`, `result`, and `history` with local component state.

Main views:
- `frontend/src/views/Home.vue`: trip request form; calls generate
- `frontend/src/views/Result.vue`: itinerary display, editing, save, export, map, weather
- `frontend/src/views/History.vue`: saved trip list/detail entry

Shared API layer:
- `frontend/src/services/api.ts`

Type mirroring:
- `frontend/src/types/index.ts`

Map UI:
- `frontend/src/components/AmapTripMap.vue`

When changing payload shape, update backend Pydantic models first, then keep the frontend TS types and API wrappers in sync.

## Important product behaviors

- Save/export flow is coupled: the frontend saves the current itinerary before navigating to export URLs.
- Weather is fetched separately from itinerary generation.
- Map rendering depends on enriched latitude/longitude fields; if the map is empty, check backend enrichment flags and returned coordinates before debugging the Vue component.
- The frontend API client defaults to `http://localhost:8000` and uses a 120s timeout.

## Testing reality in this repo

- Backend has pytest coverage across API, services, models, RAG, storage, cache, and planner agent behavior.
- Frontend currently has build/type-check scripts but no configured test script or lint script in `frontend/package.json`.
- For frontend changes, the main verification path is `npm run build` plus manual app testing against the backend.
