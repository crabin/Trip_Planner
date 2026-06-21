# AMap API Optimization Plan

## Goal
Optimize the AMap integration so trip planning can fetch richer real POI data for attractions, nearby hotels, and real food recommendations where the public AMap API supports it.

## Current Status
- Phase 1: Restore context and inspect current AMap code - complete
- Phase 2: Design supported AMap data model and service APIs - complete
- Phase 3: Implement richer POI/nearby search and normalization - complete
- Phase 4: Connect enrichment to itinerary output where schema supports it - complete
- Phase 5: Add focused tests - complete
- Phase 6: Run verification - complete
- Phase 7: Complete remaining public AMap fields and frontend display - complete
- Phase 8: Verify final AMap-only completion - complete
- Phase 9: Add configurable Meituan/Dianping local-life provider and candidate model - complete
- Phase 10: Combine providers for recommendation ranking and map candidates - complete
- Phase 11: Update frontend to show only recommended hotel/meal cards while map shows all candidates - complete
- Phase 12: Verify local-life integration path - complete

## Decisions
- Use AMap public Web Service fields only: POI id/name/type/address/location/photos/tel/business area/rating/cost/tags/distance.
- Treat AMap `cost` as reference average spend, not bookable hotel room price or inventory.
- Public AMap docs do not expose review text or official food ranking APIs; app-level lists require another provider or commercial access.
- Keep API failures non-blocking for itinerary generation.
- Meituan/Dianping integration will be configurable and optional because no stable public self-serve API docs were found; when no endpoint/key is configured, the system falls back to AMap-only enrichment.
- Below-result cards should show only recommended hotel/meal items. Candidate hotels/meals that were not selected should still appear on the map.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Ruff command failed with `No such file or directory` because paths were prefixed with `backend/` while cwd was already `backend/` | 1 | Re-run ruff from `backend/` using `app/...` and `tests/...` paths. |
| Combined tests showed explicit LLM-edited meal `海景下午茶` was overwritten by nearby restaurant enrichment | 1 | Limited meal candidate replacement to placeholder meal names only, preserving explicit user/LLM meal choices. |

## Files Expected To Change
- `backend/app/services/map_service.py`
- `backend/app/services/local_life_service.py`
- `backend/app/models/schemas.py`
- `backend/tests/test_map_service.py` or related service tests
- `backend/app/config.py`
- `backend/.env.example`
- `frontend/src/types/index.ts`
- `frontend/src/views/Result.vue`
- `frontend/src/components/AmapTripMap.vue`
- `task_plan.md`
- `findings.md`
- `progress.md`

## Verification
- `uv run pytest tests/test_map_service.py -q` - passed, 3 tests
- `uv run ruff check app/services/map_service.py app/models/schemas.py tests/test_map_service.py` - passed
- `uv run pytest tests/test_services_trip.py tests/test_models_schemas.py tests/test_map_service.py -q` - passed, 20 tests
- `uv run pytest tests -q` - passed, 59 tests, 10 warnings
- `uv run pytest tests/test_map_service.py -q` - passed, 4 tests after remaining AMap field completion
- `npm run build` - passed
- `uv run pytest tests/test_services_trip.py tests/test_models_schemas.py tests/test_map_service.py -q` - passed, 21 tests
- `uv run pytest tests -q` - passed, 60 tests, 10 warnings
- `uv run ruff check app/services/map_service.py app/services/local_life_service.py app/models/schemas.py tests/test_map_service.py tests/test_local_life_service.py` - passed
- `uv run pytest tests/test_map_service.py tests/test_local_life_service.py -q` - passed, 6 tests
- `npm run build` - passed after candidate map/frontend changes
- `uv run pytest tests/test_services_trip.py tests/test_models_schemas.py tests/test_map_service.py tests/test_local_life_service.py -q` - passed, 26 tests
- `uv run pytest tests -q` - passed, 67 tests, 10 warnings
