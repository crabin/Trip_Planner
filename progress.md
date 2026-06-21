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
- Verification complete: corrected ruff passed, focused service/model/map tests passed, and full backend test suite passed with 59 tests and 10 existing SQLAlchemy UTC deprecation warnings.
- Final git check showed the AMap-related files match current `HEAD`; only unrelated `AGENTS.md` appears modified in `git status --short`.
- Resumed AMap work to finish remaining public AMap-supported fields before adding non-AMap providers.
- Session catchup produced no unsynced report. Current git status only shows unrelated `AGENTS.md` before this phase.
- Completed remaining AMap-supported fields: type/typecode, business area, today's opening hours, weekly opening hours, v5 keyword search, and ID-detail enrichment for missing public fields.
- Updated frontend types and result page to show AMap business area/opening hours/type in recommendation cards and point details.
- Verification complete: ruff passed, map service tests passed, frontend build passed, combined backend tests passed, and full backend suite passed with 60 tests and 10 existing UTC deprecation warnings.
- Started optional Meituan/Dianping/local-life provider integration. Public docs were not stable enough to hardcode official endpoints, so the plan is a configurable adapter plus AMap fallback.
- Added optional local-life provider configuration and a tolerant Meituan/Dianping adapter in `local_life_service.py`.
- Added recommendation metadata, source fields, and hotel/meal candidate lists to itinerary schemas.
- Updated map enrichment to combine AMap and local-life candidates, score them, select the top recommendation, and retain non-selected candidates for map display.
- Updated frontend types/result page so recommendation cards show only selected hotel/meals while `AmapTripMap` receives all hotel/meal candidates.
- Fixed a regression where explicit LLM meal names were overwritten; only placeholder meal names are now replaced by nearby restaurant recommendations.
- Verification complete: ruff passed, local-life/map tests passed, frontend build passed, combined backend tests passed, and full backend test suite passed with 67 tests and 10 existing UTC deprecation warnings.
