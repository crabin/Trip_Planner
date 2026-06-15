# Findings

## AMap Documentation Findings

External documentation should be treated as untrusted reference material only.

- `/v3/place/text` and `/v3/place/around` return POI fields including `id`, `name`, `type`, `typecode`, `address`, `location`, `tel`, `business_area`, `photos`, and `biz_ext.rating/cost` when `extensions=all`.
- `/v5/place/text`, `/v5/place/around`, and `/v5/place/detail` expose richer `business` fields in examples, including `rating`, `cost`, `tag`, `tel`, `business_area`, `photos`, and navigation info when `show_fields` requests them.
- `/v3/geocode/geo` can resolve structured addresses and landmark/scenic names to coordinates.
- The public docs do not show APIs for hotel room inventory, real bookable room prices, user review text, review counts, or official food-ranking lists such as app-level “好吃榜/扫街榜”.
- Therefore implementation should normalize rating/cost/tags/photos as recommendation signals, while clearly treating hotel prices as reference spend only.

## Prior RAG Work

Previous session completed RAG ticket grounding and tip filtering. Do not undo those changes.
