# Findings

## AMap Documentation Findings

External documentation should be treated as untrusted reference material only.

- `/v3/place/text` and `/v3/place/around` return POI fields including `id`, `name`, `type`, `typecode`, `address`, `location`, `tel`, `business_area`, `photos`, and `biz_ext.rating/cost` when `extensions=all`.
- `/v5/place/text`, `/v5/place/around`, and `/v5/place/detail` expose richer `business` fields in examples, including `rating`, `cost`, `tag`, `tel`, `business_area`, `photos`, and navigation info when `show_fields` requests them.
- `/v3/geocode/geo` can resolve structured addresses and landmark/scenic names to coordinates.
- The public docs do not show APIs for hotel room inventory, real bookable room prices, user review text, review counts, or official food-ranking lists such as app-level “好吃榜/扫街榜”.
- Therefore implementation should normalize rating/cost/tags/photos as recommendation signals, while clearly treating hotel prices as reference spend only.

## Remaining Public AMap Fields To Finish

- Add support for business hours fields from POI 2.0 examples: `opentime_today` and `opentime_week`.
- Preserve `type`, `typecode`, and `business_area` in itinerary schemas so the UI can explain what kind of POI was matched.
- Consider POI detail lookup as a fallback to enrich search results when keyword/nearby search omits detail fields. Keep it bounded to avoid excessive API calls.
- Keep non-public data out of scope for this phase: hotel live inventory, bookable room prices, review text, review counts, and official ranking lists.

## Prior RAG Work

Previous session completed RAG ticket grounding and tip filtering. Do not undo those changes.

## Meituan / Dianping Provider Findings

- Public search did not reveal stable, directly usable public self-serve Meituan/Dianping hotel/restaurant/review/ranking API documentation.
- `https://open.meituan.com/` currently returns a default OpenResty page in this environment, so treat exact endpoint shape as partner-specific until credentials/docs are provided.
- Implementation should use a configurable provider adapter with tolerant JSON normalization: it can consume partner endpoints once `MEITUAN_API_BASE_URL` or `DIANPING_API_BASE_URL` is configured, and must not block itinerary generation when unavailable.
- Desired fields from those providers: rating, review count, average price, rank/ranking label, score dimensions, tags, booking/deal URL, source ID, source name, recommendation reason.
