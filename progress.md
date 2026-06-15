# Progress

## 2026-06-15

- Started AMap API optimization using `planning-with-files`.
- Restored existing planning context and replaced the completed RAG plan with a new AMap-focused plan.
- Recorded AMap public API capability boundaries in `findings.md`: POI nearby/details can provide rating/cost/tags/photos, but not real hotel inventory/prices, review text, or official food ranking lists.
- Observed existing uncommitted work in the repository; will keep AMap edits scoped and avoid reverting unrelated changes.
- Added map schema fields for POI metadata: rating, reference average cost, tags, phone, distance, images and POI IDs for spots/meals/hotels.
- Implemented normalized AMap POI parsing, v5 nearby search with v3 fallback, nearby hotel/restaurant recommendation helpers, and itinerary enrichment for nearby lodging/food.
- Added focused map service tests for POI normalization, v5 nearby ranking, and itinerary enrichment.
- Verification: `uv run pytest tests/test_map_service.py -q` passed. First ruff attempt failed due to wrong paths from the `backend/` cwd; rerunning with corrected paths next.
