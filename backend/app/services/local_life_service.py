from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import (
    DIANPING_API_BASE_URL,
    DIANPING_API_KEY,
    ENABLE_LOCAL_LIFE_ENRICHMENT,
    LOCAL_LIFE_TIMEOUT_SECONDS,
    MEITUAN_API_BASE_URL,
    MEITUAN_API_KEY,
    REDIS_MAP_TTL_SECONDS,
)
from app.services.cache_service import get_cached_json, set_cached_json


logger = logging.getLogger(__name__)


ProviderConfig = tuple[str, str, str]


def _provider_configs() -> list[ProviderConfig]:
    providers: list[ProviderConfig] = []
    if MEITUAN_API_BASE_URL and MEITUAN_API_KEY:
        providers.append(("meituan", MEITUAN_API_BASE_URL.rstrip("/"), MEITUAN_API_KEY))
    if DIANPING_API_BASE_URL and DIANPING_API_KEY:
        providers.append(("dianping", DIANPING_API_BASE_URL.rstrip("/"), DIANPING_API_KEY))
    return providers


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            joined = "、".join(str(item).strip() for item in value if str(item).strip())
            if joined:
                return joined
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_float(value: Any) -> float | None:
    if value in (None, "", []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    parsed = _parse_float(value)
    return int(parsed) if parsed is not None else None


def _split_tags(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value)
    for separator in [";", "|", ",", "，"]:
        text = text.replace(separator, "、")
    return [item.strip() for item in text.split("、") if item.strip()]


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        payload.get("items"),
        payload.get("results"),
        payload.get("data"),
        payload.get("pois"),
        payload.get("businesses"),
        payload.get("hotels"),
        payload.get("shops"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        if isinstance(candidate, dict):
            for key in ["items", "results", "list", "records", "shops", "hotels"]:
                nested = candidate.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
    return []


def _normalize_item(item: dict[str, Any], provider: str, category: str) -> dict[str, Any]:
    latitude = _parse_float(item.get("latitude") or item.get("lat"))
    longitude = _parse_float(item.get("longitude") or item.get("lng") or item.get("lon"))
    return {
        "data_source": provider,
        "category": category,
        "source_id": _first_text(item.get("id"), item.get("shop_id"), item.get("business_id")),
        "name": _first_text(item.get("name"), item.get("shop_name"), item.get("title")),
        "address": _first_text(item.get("address"), item.get("addr")),
        "latitude": latitude,
        "longitude": longitude,
        "image_url": _first_text(item.get("image_url"), item.get("photo_url"), item.get("cover")),
        "map_rating": _parse_float(item.get("rating") or item.get("score") or item.get("avg_rating")),
        "map_average_cost": _parse_float(
            item.get("avg_price") or item.get("average_cost") or item.get("price")
        ),
        "map_tags": _split_tags(item.get("tags") or item.get("categories")),
        "map_tel": _first_text(item.get("tel"), item.get("phone")),
        "map_distance_meters": _parse_float(item.get("distance") or item.get("distance_meters")),
        "map_business_area": _first_text(item.get("business_area"), item.get("area")),
        "map_open_time_today": _first_text(item.get("open_time"), item.get("opentime_today")),
        "source_url": _first_text(item.get("url"), item.get("detail_url"), item.get("booking_url")),
        "review_count": _parse_int(item.get("review_count") or item.get("comment_count")),
        "ranking_label": _first_text(item.get("ranking_label"), item.get("rank"), item.get("badge")),
    }


def fetch_local_life_candidates(
    *,
    longitude: float,
    latitude: float,
    category: str,
    radius: int,
    page_size: int = 10,
) -> list[dict[str, Any]]:
    """Fetch optional Meituan/Dianping partner candidates around a coordinate."""
    if not ENABLE_LOCAL_LIFE_ENRICHMENT:
        return []

    providers = _provider_configs()
    if not providers:
        return []

    all_results: list[dict[str, Any]] = []
    for provider, base_url, api_key in providers:
        cache_key = (
            "local-life:"
            f"{provider}:{category}:{longitude:.6f},{latitude:.6f}:{radius}:{page_size}"
        )
        cached_value = get_cached_json(cache_key)
        if cached_value is not None:
            all_results.extend(cached_value)
            continue

        params = {
            "key": api_key,
            "category": category,
            "longitude": longitude,
            "latitude": latitude,
            "radius": radius,
            "limit": page_size,
        }
        try:
            with httpx.Client(timeout=LOCAL_LIFE_TIMEOUT_SECONDS) as client:
                response = client.get(f"{base_url}/search", params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("%s local-life search failed: %s", provider, exc)
            continue

        results = [
            _normalize_item(item, provider=provider, category=category)
            for item in _extract_items(payload)
        ]
        set_cached_json(cache_key, results, expire_seconds=REDIS_MAP_TTL_SECONDS)
        all_results.extend(results)

    return all_results
