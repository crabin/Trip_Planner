from __future__ import annotations

from typing import Any

from app.services.cache_service import get_cached_json, set_cached_json
from app.services.map_service import _distance_meters, _normalize_cache_text, _request_amap, geocode_address


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def get_location_suggestions(keyword: str, limit: int = 10) -> list[dict[str, str]]:
    """Return remote place/city suggestions without shipping a full city list to the frontend."""
    normalized_keyword = keyword.strip()
    if len(normalized_keyword) < 1:
        return []

    safe_limit = max(1, min(limit, 20))
    cache_key = f"location:suggestions:{_normalize_cache_text(normalized_keyword)}:{safe_limit}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        return cached_value

    payload = _request_amap(
        "/assistant/inputtips",
        {
            "keywords": normalized_keyword,
            "datatype": "all",
            "output": "JSON",
        },
    )

    suggestions: list[dict[str, str]] = []
    seen: set[str] = set()
    for tip in payload.get("tips", []):
        name = _first_text(tip.get("name")).strip()
        if not name:
            continue
        district = _first_text(tip.get("district")).strip()
        adcode = _first_text(tip.get("adcode")).strip()
        key = f"{name}:{adcode or district}"
        if key in seen:
            continue
        seen.add(key)
        label = f"{name} · {district}" if district and district not in name else name
        suggestions.append(
            {
                "label": label,
                "value": name,
                "district": district,
                "adcode": adcode,
            }
        )
        if len(suggestions) >= safe_limit:
            break

    set_cached_json(cache_key, suggestions, expire_seconds=86400)
    return suggestions


def check_destination_span(destinations: list[str]) -> dict[str, Any]:
    """Geocode destinations and return the largest pairwise distance in kilometers."""
    unique_destinations = list(dict.fromkeys(item.strip() for item in destinations if item.strip()))
    resolved: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for destination in unique_destinations:
        geocode = geocode_address(destination, city=destination)
        if not geocode or geocode.get("latitude") is None or geocode.get("longitude") is None:
            unresolved.append(destination)
            continue
        resolved.append(
            {
                "name": destination,
                "latitude": geocode["latitude"],
                "longitude": geocode["longitude"],
                "formatted_address": geocode.get("formatted_address") or destination,
            }
        )

    max_distance_km = 0.0
    max_pair: list[str] = []
    for index, origin in enumerate(resolved):
        for destination in resolved[index + 1 :]:
            distance_km = _distance_meters(
                latitude_a=float(origin["latitude"]),
                longitude_a=float(origin["longitude"]),
                latitude_b=float(destination["latitude"]),
                longitude_b=float(destination["longitude"]),
            ) / 1000
            if distance_km > max_distance_km:
                max_distance_km = distance_km
                max_pair = [origin["name"], destination["name"]]

    return {
        "max_distance_km": round(max_distance_km, 1),
        "max_pair": max_pair,
        "resolved": resolved,
        "unresolved": unresolved,
        "is_large_span": max_distance_km >= 500,
    }
