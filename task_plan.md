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

## Decisions
- Use AMap public Web Service fields only: POI id/name/type/address/location/photos/tel/business area/rating/cost/tags/distance.
- Treat AMap `cost` as reference average spend, not bookable hotel room price or inventory.
- Public AMap docs do not expose review text or official food ranking APIs; app-level lists require another provider or commercial access.
- Keep API failures non-blocking for itinerary generation.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Ruff command failed with `No such file or directory` because paths were prefixed with `backend/` while cwd was already `backend/` | 1 | Re-run ruff from `backend/` using `app/...` and `tests/...` paths. |

## Files Expected To Change
- `backend/app/services/map_service.py`
- `backend/app/models/schemas.py`
- `backend/tests/test_map_service.py` or related service tests
- `task_plan.md`
- `findings.md`
- `progress.md`

## Verification
- `uv run pytest tests/test_map_service.py -q` - passed, 3 tests
- `uv run ruff check app/services/map_service.py app/models/schemas.py tests/test_map_service.py` - passed
- `uv run pytest tests/test_services_trip.py tests/test_models_schemas.py tests/test_map_service.py -q` - passed, 20 tests
- `uv run pytest tests -q` - passed, 59 tests, 10 warnings
