from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import (
    AMAP_API_KEY,
    AMAP_BASE_URL,
    AMAP_DEFAULT_CITY,
    AMAP_TIMEOUT_SECONDS,
    REDIS_MAP_TTL_SECONDS,
)
from app.models.schemas import HotelItem, Itinerary, MealItem, SpotItem, TransportItem
from app.services.cache_service import get_cached_json, set_cached_json
from app.services.local_life_service import fetch_local_life_candidates


logger = logging.getLogger(__name__)


def _ensure_amap_api_key() -> None:
    """确保当前环境已经配置高德地图 Key。"""
    if not AMAP_API_KEY:
        raise RuntimeError("当前环境未配置 AMAP_API_KEY，无法调用高德地图服务。")


def _build_client() -> httpx.Client:
    """创建访问高德 HTTP API 的客户端。"""
    return httpx.Client(timeout=AMAP_TIMEOUT_SECONDS)


def _request_amap(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """调用高德地图 API 并返回 JSON 结果。"""
    _ensure_amap_api_key()

    request_params = {
        "key": AMAP_API_KEY,
        **params,
    }

    with _build_client() as client:
        response = client.get(f"{AMAP_BASE_URL}{path}", params=request_params)
        response.raise_for_status()
        payload = response.json()

    if payload.get("status") != "1":
        info = payload.get("info", "未知错误")
        raise RuntimeError(f"高德地图接口调用失败：{info}")

    return payload


def _build_amap_url(path: str, api_version: str = "v3") -> str:
    """根据配置的 base url 拼出指定版本的高德 Web 服务地址。"""
    base_url = AMAP_BASE_URL.rstrip("/")
    if api_version and base_url.endswith(("/v3", "/v5")):
        base_url = f"{base_url.rsplit('/', 1)[0]}/{api_version}"
    return f"{base_url}{path}"


def _request_amap_versioned(
    path: str,
    params: dict[str, Any],
    api_version: str = "v3",
) -> dict[str, Any]:
    """调用指定版本的高德地图 API 并返回 JSON 结果。"""
    _ensure_amap_api_key()

    request_params = {
        "key": AMAP_API_KEY,
        **params,
    }

    with _build_client() as client:
        response = client.get(_build_amap_url(path, api_version), params=request_params)
        response.raise_for_status()
        payload = response.json()

    if str(payload.get("status")) != "1":
        info = payload.get("info", "未知错误")
        raise RuntimeError(f"高德地图接口调用失败：{info}")

    return payload


def _parse_float(value: str | None) -> float | None:
    """把字符串安全转换成浮点数。"""
    if value in (None, "", []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_location(location: str | None) -> tuple[float | None, float | None]:
    """把高德返回的 '经度,纬度' 文本拆成两个浮点数。"""
    if not location or "," not in location:
        return None, None

    longitude_text, latitude_text = location.split(",", 1)
    return _parse_float(latitude_text), _parse_float(longitude_text)


def _normalize_cache_text(value: str | None) -> str:
    """把缓存 key 里用到的文本做简单标准化。"""
    if value is None:
        return ""
    return value.strip().lower()


def _first_text(value: Any) -> str | None:
    """把高德可能返回的空数组、字符串或数字统一成可用文本。"""
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _extract_poi_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """兼容 v3 与 v5 的 POI 列表响应形状。"""
    pois = payload.get("pois", [])
    if isinstance(pois, list):
        return [poi for poi in pois if isinstance(poi, dict)]
    if isinstance(pois, dict):
        poi_value = pois.get("poi", [])
        if isinstance(poi_value, list):
            return [poi for poi in poi_value if isinstance(poi, dict)]
        if isinstance(poi_value, dict):
            return [poi_value]
    return []


def _extract_photos(poi: dict[str, Any], business: dict[str, Any]) -> list[dict[str, Any]]:
    photos = poi.get("photos")
    if not isinstance(photos, list):
        navi = business.get("navi") if isinstance(business.get("navi"), dict) else {}
        photos = navi.get("photos") if isinstance(navi.get("photos"), list) else []
    return [photo for photo in photos if isinstance(photo, dict)]


def _split_tags(value: Any) -> list[str]:
    text = _first_text(value)
    if not text:
        return []
    separators = [";", "|", ",", "，"]
    values = [text]
    for separator in separators:
        next_values: list[str] = []
        for item in values:
            next_values.extend(item.split(separator))
        values = next_values
    return [item.strip() for item in values if item.strip()]


def _normalize_poi(poi: dict[str, Any]) -> dict[str, Any]:
    """把高德 POI 转成应用内部稳定字段。"""
    business = poi.get("business") if isinstance(poi.get("business"), dict) else {}
    biz_ext = poi.get("biz_ext") if isinstance(poi.get("biz_ext"), dict) else {}
    latitude, longitude = _split_location(_first_text(poi.get("location")))
    photos = _extract_photos(poi, business)
    first_photo = photos[0] if photos else {}

    rating = _parse_float(_first_text(business.get("rating") or biz_ext.get("rating")))
    average_cost = _parse_float(_first_text(business.get("cost") or biz_ext.get("cost")))

    business_area = _first_text(business.get("business_area") or poi.get("business_area"))
    open_time_today = _first_text(business.get("opentime_today") or poi.get("opentime_today"))
    open_time_week = _first_text(business.get("opentime_week") or poi.get("opentime_week"))
    poi_type = _first_text(poi.get("type"))
    typecode = _first_text(poi.get("typecode"))

    return {
        "name": _first_text(poi.get("name")),
        "address": _first_text(poi.get("address")),
        "cityname": _first_text(poi.get("cityname")),
        "adname": _first_text(poi.get("adname")),
        "type": poi_type,
        "typecode": typecode,
        "poi_id": _first_text(poi.get("id")),
        "image_url": _first_text(first_photo.get("url")),
        "latitude": latitude,
        "longitude": longitude,
        "business_area": business_area,
        "map_rating": rating,
        "map_average_cost": average_cost,
        "map_tags": _split_tags(business.get("tag") or poi.get("tag")),
        "map_tel": _first_text(business.get("tel") or poi.get("tel")),
        "map_distance_meters": _parse_float(_first_text(poi.get("distance"))),
        "map_type": poi_type,
        "map_typecode": typecode,
        "map_business_area": business_area,
        "map_open_time_today": open_time_today,
        "map_open_time_week": open_time_week,
    }


def _merge_place_data(base: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any]:
    """用 POI 详情补齐搜索结果，保留搜索里的距离等上下文字段。"""
    if not detail:
        return base
    merged = dict(base)
    for key, value in detail.items():
        if value not in (None, "", []):
            if key == "map_distance_meters" and merged.get(key) is not None:
                continue
            merged[key] = value
    return merged


def _needs_place_detail(place: dict[str, Any]) -> bool:
    """判断搜索结果是否缺少值得再查详情的公开高德字段。"""
    detail_keys = [
        "image_url",
        "map_rating",
        "map_average_cost",
        "map_business_area",
        "map_open_time_today",
        "map_open_time_week",
    ]
    return any(place.get(key) in (None, "", []) for key in detail_keys)


def _rank_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """优先选择评分较高、距离较近、信息更完整的 POI。"""

    def score(place: dict[str, Any]) -> tuple[float, float, int]:
        rating = place.get("map_rating") or 0.0
        distance = place.get("map_distance_meters")
        has_photo = 1 if place.get("image_url") else 0
        return (float(rating), -float(distance if distance is not None else 999999), has_photo)

    return sorted(places, key=score, reverse=True)


def _recommendation_score(place: dict[str, Any]) -> float:
    rating = float(place.get("map_rating") or 0)
    review_count = float(place.get("review_count") or 0)
    distance = float(place.get("map_distance_meters") or 3000)
    source_bonus = 1.0 if place.get("data_source") in {"meituan", "dianping"} else 0.0
    rank_bonus = 0.8 if place.get("ranking_label") else 0.0
    review_bonus = min(review_count / 500, 1.5)
    distance_bonus = max(0.0, 1.2 - min(distance, 3000) / 3000)
    return round(rating * 2 + review_bonus + distance_bonus + source_bonus + rank_bonus, 2)


def _recommendation_reason(place: dict[str, Any]) -> str:
    parts: list[str] = []
    if place.get("ranking_label"):
        parts.append(str(place["ranking_label"]))
    if place.get("map_rating") is not None:
        parts.append(f"评分 {float(place['map_rating']):.1f}")
    if place.get("review_count") is not None:
        parts.append(f"{int(place['review_count'])} 条评价")
    if place.get("map_distance_meters") is not None:
        distance = float(place["map_distance_meters"])
        parts.append(f"距离约 {distance / 1000:.1f} km" if distance >= 1000 else f"距离约 {distance:.0f} m")
    if place.get("map_average_cost") is not None:
        parts.append(f"参考价 ¥{float(place['map_average_cost']):.0f}")
    if place.get("data_source") in {"meituan", "dianping"}:
        parts.append("来自美团/点评合作数据")
    return "，".join(parts) if parts else "综合位置、价格和地图信息推荐"


def _dedupe_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for place in places:
        name = str(place.get("name") or "").strip().lower()
        address = str(place.get("address") or "").strip().lower()
        key = f"{name}:{address}" if name or address else str(place.get("poi_id") or place.get("source_id"))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(place)
    return deduped


def _rank_recommendation_candidates(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for place in _dedupe_places(places):
        candidate = dict(place)
        candidate.setdefault("data_source", "amap")
        candidate["recommendation_score"] = _recommendation_score(candidate)
        candidate["recommendation_reason"] = _recommendation_reason(candidate)
        enriched.append(candidate)
    return sorted(enriched, key=lambda item: item["recommendation_score"], reverse=True)


def _copy_place_to_spot(spot: SpotItem, place: dict[str, Any]) -> None:
    spot.address = place.get("address") or spot.address
    spot.image_url = place.get("image_url") or spot.image_url
    spot.latitude = place.get("latitude")
    spot.longitude = place.get("longitude")
    spot.poi_id = place.get("poi_id") or spot.poi_id
    spot.map_rating = place.get("map_rating")
    spot.map_average_cost = place.get("map_average_cost")
    spot.map_tags = place.get("map_tags") or spot.map_tags
    spot.map_tel = place.get("map_tel")
    spot.map_distance_meters = place.get("map_distance_meters")
    spot.map_type = place.get("map_type")
    spot.map_typecode = place.get("map_typecode")
    spot.map_business_area = place.get("map_business_area")
    spot.map_open_time_today = place.get("map_open_time_today")
    spot.map_open_time_week = place.get("map_open_time_week")


def _copy_place_to_hotel(hotel: HotelItem, place: dict[str, Any]) -> None:
    if place.get("name"):
        hotel.name = place["name"]
    hotel.address = place.get("address") or hotel.address
    hotel.latitude = place.get("latitude")
    hotel.longitude = place.get("longitude")
    hotel.image_url = place.get("image_url") or hotel.image_url
    hotel.poi_id = place.get("poi_id") or hotel.poi_id
    hotel.map_rating = place.get("map_rating")
    hotel.map_average_cost = place.get("map_average_cost")
    hotel.map_tags = place.get("map_tags") or hotel.map_tags
    hotel.map_tel = place.get("map_tel")
    hotel.map_distance_meters = place.get("map_distance_meters")
    hotel.map_type = place.get("map_type")
    hotel.map_typecode = place.get("map_typecode")
    hotel.map_business_area = place.get("map_business_area")
    hotel.map_open_time_today = place.get("map_open_time_today")
    hotel.map_open_time_week = place.get("map_open_time_week")
    hotel.data_source = place.get("data_source") or hotel.data_source or "amap"
    hotel.source_id = place.get("source_id") or place.get("poi_id") or hotel.source_id
    hotel.source_url = place.get("source_url") or hotel.source_url
    hotel.review_count = place.get("review_count")
    hotel.ranking_label = place.get("ranking_label")
    hotel.recommendation_score = place.get("recommendation_score")
    hotel.recommendation_reason = place.get("recommendation_reason")
    if place.get("business_area") and not hotel.location:
        hotel.location = place["business_area"]


def _copy_place_to_meal(meal: MealItem, place: dict[str, Any]) -> None:
    if place.get("name"):
        meal.name = place["name"]
    meal.address = place.get("address") or meal.address
    meal.latitude = place.get("latitude")
    meal.longitude = place.get("longitude")
    meal.image_url = place.get("image_url") or meal.image_url
    meal.poi_id = place.get("poi_id") or meal.poi_id
    meal.map_rating = place.get("map_rating")
    meal.map_average_cost = place.get("map_average_cost")
    meal.map_tags = place.get("map_tags") or meal.map_tags
    meal.map_tel = place.get("map_tel")
    meal.map_distance_meters = place.get("map_distance_meters")
    meal.map_type = place.get("map_type")
    meal.map_typecode = place.get("map_typecode")
    meal.map_business_area = place.get("map_business_area")
    meal.map_open_time_today = place.get("map_open_time_today")
    meal.map_open_time_week = place.get("map_open_time_week")
    meal.data_source = place.get("data_source") or meal.data_source or "amap"
    meal.source_id = place.get("source_id") or place.get("poi_id") or meal.source_id
    meal.source_url = place.get("source_url") or meal.source_url
    meal.review_count = place.get("review_count")
    meal.ranking_label = place.get("ranking_label")
    meal.recommendation_score = place.get("recommendation_score")
    meal.recommendation_reason = place.get("recommendation_reason")

    detail_parts: list[str] = []
    if meal.notes:
        detail_parts.append(meal.notes)
    if meal.map_rating is not None:
        detail_parts.append(f"高德评分 {meal.map_rating:g}")
    if meal.map_average_cost is not None:
        detail_parts.append(f"参考人均 ¥{meal.map_average_cost:g}")
    if meal.map_tags:
        detail_parts.append("标签：" + "、".join(meal.map_tags[:3]))
    if meal.map_open_time_today:
        detail_parts.append(f"今日营业：{meal.map_open_time_today}")
    meal.notes = "；".join(detail_parts) if detail_parts else meal.notes


def _hotel_from_place(place: dict[str, Any], level: str | None = None) -> HotelItem:
    hotel = HotelItem(name=str(place.get("name") or "住宿候选"), level=level)
    _copy_place_to_hotel(hotel, place)
    return hotel


def _meal_from_place(place: dict[str, Any], meal_type: str = "餐饮") -> MealItem:
    meal = MealItem(name=str(place.get("name") or "餐饮候选"), meal_type=meal_type)
    _copy_place_to_meal(meal, place)
    return meal


def _is_placeholder_meal_name(name: str) -> bool:
    """识别规则生成的泛化餐饮名，避免覆盖用户或 LLM 明确指定的餐厅。"""
    placeholder_keywords = [
        "特色餐饮",
        "餐饮推荐",
        "午餐推荐",
        "晚餐推荐",
        "早餐推荐",
        "美食推荐",
        "简餐",
    ]
    return any(keyword in name for keyword in placeholder_keywords)


def geocode_address(address: str, city: str | None = None) -> dict[str, Any] | None:
    """根据地址获取经纬度信息。"""
    cache_key = (
        f"map:geocode:{_normalize_cache_text(address)}:{_normalize_cache_text(city or AMAP_DEFAULT_CITY)}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("map geocode cache hit: address=%s city=%s", address, city or AMAP_DEFAULT_CITY)
        return cached_value
    logger.info("map geocode cache miss: address=%s city=%s", address, city or AMAP_DEFAULT_CITY)

    payload = _request_amap(
        "/geocode/geo",
        {
            "address": address,
            "city": city or AMAP_DEFAULT_CITY,
        },
    )

    geocodes = payload.get("geocodes", [])
    if not geocodes:
        return None

    first = geocodes[0]
    latitude, longitude = _split_location(first.get("location"))
    result = {
        "formatted_address": first.get("formatted_address", address),
        "province": first.get("province"),
        "city": first.get("city"),
        "district": first.get("district"),
        "adcode": first.get("adcode"),
        "latitude": latitude,
        "longitude": longitude,
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result


def search_places(
    keyword: str,
    city: str | None = None,
    page_size: int = 5,
) -> list[dict[str, Any]]:
    """根据关键词搜索 POI。"""
    cache_key = (
        f"map:place:{_normalize_cache_text(keyword)}:{_normalize_cache_text(city or AMAP_DEFAULT_CITY)}:{page_size}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("map place cache hit: keyword=%s city=%s", keyword, city or AMAP_DEFAULT_CITY)
        return cached_value
    logger.info("map place cache miss: keyword=%s city=%s", keyword, city or AMAP_DEFAULT_CITY)

    try:
        payload = _request_amap_versioned(
            "/place/text",
            {
                "keywords": keyword,
                "region": city or AMAP_DEFAULT_CITY,
                "show_fields": "business,photos",
                "page_size": page_size,
                "page_num": 1,
                "output": "JSON",
            },
            api_version="v5",
        )
    except RuntimeError:
        payload = _request_amap(
            "/place/text",
            {
                "keywords": keyword,
                "city": city or AMAP_DEFAULT_CITY,
                "offset": page_size,
                "page": 1,
                "extensions": "all",
            },
        )

    results = [_normalize_poi(poi) for poi in _extract_poi_list(payload)]

    set_cached_json(cache_key, results, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return results


def get_place_detail(poi_id: str) -> dict[str, Any] | None:
    """根据 POI ID 查询高德详情。"""
    cache_key = f"map:place-detail:{_normalize_cache_text(poi_id)}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("map place detail cache hit: poi_id=%s", poi_id)
        return cached_value
    logger.info("map place detail cache miss: poi_id=%s", poi_id)

    try:
        payload = _request_amap_versioned(
            "/place/detail",
            {
                "id": poi_id,
                "show_fields": "business,photos",
                "output": "JSON",
            },
            api_version="v5",
        )
    except RuntimeError:
        payload = _request_amap(
            "/place/detail",
            {
                "id": poi_id,
                "extensions": "all",
                "output": "JSON",
            },
        )

    pois = _extract_poi_list(payload)
    if not pois:
        return None

    result = _normalize_poi(pois[0])
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result


def search_nearby_places(
    longitude: float,
    latitude: float,
    poi_types: str | None = None,
    keywords: str | None = None,
    radius: int = 3000,
    page_size: int = 10,
) -> list[dict[str, Any]]:
    """搜索指定坐标附近的 POI，并返回按评分/距离排序后的结果。"""
    cache_key = (
        "map:nearby:"
        f"{longitude:.6f},{latitude:.6f}:"
        f"{_normalize_cache_text(poi_types)}:{_normalize_cache_text(keywords)}:"
        f"{radius}:{page_size}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("map nearby cache hit: longitude=%s latitude=%s", longitude, latitude)
        return cached_value
    logger.info("map nearby cache miss: longitude=%s latitude=%s", longitude, latitude)

    try:
        payload = _request_amap_versioned(
            "/place/around",
            {
                "location": f"{longitude},{latitude}",
                "types": poi_types or "",
                "keywords": keywords or "",
                "radius": radius,
                "sortrule": "distance",
                "show_fields": "business,photos",
                "page_size": page_size,
                "page_num": 1,
                "output": "JSON",
            },
            api_version="v5",
        )
    except RuntimeError:
        payload = _request_amap(
            "/place/around",
            {
                "location": f"{longitude},{latitude}",
                "types": poi_types or "",
                "keywords": keywords or "",
                "radius": radius,
                "offset": page_size,
                "page": 1,
                "extensions": "all",
                "output": "JSON",
            },
        )

    results = _rank_places([_normalize_poi(poi) for poi in _extract_poi_list(payload)])
    set_cached_json(cache_key, results, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return results


def recommend_nearby_hotels(
    longitude: float,
    latitude: float,
    radius: int = 3000,
    page_size: int = 10,
) -> list[dict[str, Any]]:
    """推荐参考点附近的住宿 POI。"""
    return search_nearby_places(
        longitude=longitude,
        latitude=latitude,
        poi_types="100000",
        radius=radius,
        page_size=page_size,
    )


def recommend_nearby_restaurants(
    longitude: float,
    latitude: float,
    radius: int = 2000,
    page_size: int = 10,
) -> list[dict[str, Any]]:
    """推荐参考点附近的餐饮 POI。"""
    return search_nearby_places(
        longitude=longitude,
        latitude=latitude,
        poi_types="050000",
        radius=radius,
        page_size=page_size,
    )


def estimate_route(
    origin_longitude: float,
    origin_latitude: float,
    destination_longitude: float,
    destination_latitude: float,
) -> dict[str, Any] | None:
    """估算两点之间的驾车距离和耗时。"""
    cache_key = (
        "map:route:"
        f"{origin_longitude:.6f},{origin_latitude:.6f}:"
        f"{destination_longitude:.6f},{destination_latitude:.6f}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info(
            "map route cache hit: origin=%s,%s destination=%s,%s",
            origin_longitude,
            origin_latitude,
            destination_longitude,
            destination_latitude,
        )
        return cached_value
    logger.info(
        "map route cache miss: origin=%s,%s destination=%s,%s",
        origin_longitude,
        origin_latitude,
        destination_longitude,
        destination_latitude,
    )

    payload = _request_amap(
        "/direction/driving",
        {
            "origin": f"{origin_longitude},{origin_latitude}",
            "destination": f"{destination_longitude},{destination_latitude}",
            "strategy": 0,
        },
    )

    route = payload.get("route", {})
    paths = route.get("paths", [])
    if not paths:
        return None

    first_path = paths[0]
    distance_meters = _parse_float(first_path.get("distance"))
    duration_seconds = _parse_float(first_path.get("duration"))

    result = {
        "distance_meters": distance_meters,
        "distance_km": round(distance_meters / 1000, 2) if distance_meters is not None else None,
        "duration_seconds": duration_seconds,
        "estimated_minutes": round(duration_seconds / 60) if duration_seconds is not None else None,
        "taxi_cost": _parse_float(route.get("taxi_cost")),
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result


def _pick_best_place(keyword: str, city: str | None = None) -> dict[str, Any] | None:
    """优先从 POI 搜索里选取第一条结果。"""
    results = search_places(keyword=keyword, city=city, page_size=1)
    if not results:
        return None
    best_place = results[0]
    poi_id = best_place.get("poi_id")
    if poi_id and _needs_place_detail(best_place):
        try:
            return _merge_place_data(best_place, get_place_detail(poi_id))
        except Exception:
            return best_place
    return best_place


def _pick_first_available_place(
    keywords: list[str | None],
    city: str | None = None,
) -> dict[str, Any] | None:
    seen: set[str] = set()
    for keyword in keywords:
        normalized = (keyword or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        place = _pick_best_place(normalized, city=city)
        if place is not None:
            return place
    return None


def _enrich_spot(spot: SpotItem, city: str | None = None) -> bool:
    """补全单个景点的地址、经纬度和 POI 信息。"""
    place = _pick_first_available_place(
        [spot.map_query, spot.name, spot.location],
        city=city,
    )

    if place is None:
        query_address = spot.address or spot.location or spot.name
        geocode = geocode_address(query_address, city=city)
        if geocode is None:
            return False
        spot.address = geocode.get("formatted_address") or spot.address
        spot.latitude = geocode.get("latitude")
        spot.longitude = geocode.get("longitude")
        return True

    _copy_place_to_spot(spot, place)
    return True


def _enrich_meal(meal: MealItem, city: str | None = None) -> bool:
    """按 LLM/报告给出的餐饮关键词补全单个餐饮 POI。"""
    place = _pick_first_available_place(
        [meal.map_query, meal.name, meal.address],
        city=city,
    )
    if place is None:
        return False
    _copy_place_to_meal(meal, place)
    return True


def _enrich_hotel(hotel: HotelItem, city: str | None = None) -> bool:
    """补全单个酒店的地址和经纬度。"""
    place = _pick_first_available_place(
        [hotel.map_query, hotel.name, hotel.location],
        city=city,
    )

    if place is None:
        query_address = hotel.address or hotel.location or hotel.name
        geocode = geocode_address(query_address, city=city)
        if geocode is None:
            return False
        hotel.address = geocode.get("formatted_address") or hotel.address
        hotel.latitude = geocode.get("latitude")
        hotel.longitude = geocode.get("longitude")
        return True

    _copy_place_to_hotel(hotel, place)
    return True


def _enrich_hotel_near_spot(hotel: HotelItem, spot: SpotItem) -> bool:
    """基于景点坐标推荐附近住宿。"""
    if spot.latitude is None or spot.longitude is None:
        return False
    places = recommend_nearby_hotels(
        longitude=spot.longitude,
        latitude=spot.latitude,
    )
    places.extend(
        fetch_local_life_candidates(
            longitude=spot.longitude,
            latitude=spot.latitude,
            category="hotel",
            radius=3000,
            page_size=10,
        )
    )
    places = _rank_recommendation_candidates(places)
    if not places:
        return False
    _copy_place_to_hotel(hotel, places[0])
    hotel.is_recommended = True
    return True


def _enrich_meal_near_spot(meal: MealItem, spot: SpotItem) -> bool:
    """基于景点坐标推荐附近餐厅。"""
    if not _is_placeholder_meal_name(meal.name):
        return False
    if spot.latitude is None or spot.longitude is None:
        return False
    places = recommend_nearby_restaurants(
        longitude=spot.longitude,
        latitude=spot.latitude,
    )
    places.extend(
        fetch_local_life_candidates(
            longitude=spot.longitude,
            latitude=spot.latitude,
            category="restaurant",
            radius=2000,
            page_size=10,
        )
    )
    places = _rank_recommendation_candidates(places)
    if not places:
        return False
    _copy_place_to_meal(meal, places[0])
    meal.is_recommended = True
    return True


def _build_hotel_candidates_near_spot(hotel: HotelItem | None, spot: SpotItem) -> list[HotelItem]:
    if spot.latitude is None or spot.longitude is None:
        return []
    places = recommend_nearby_hotels(longitude=spot.longitude, latitude=spot.latitude)
    places.extend(
        fetch_local_life_candidates(
            longitude=spot.longitude,
            latitude=spot.latitude,
            category="hotel",
            radius=3000,
            page_size=10,
        )
    )
    ranked = _rank_recommendation_candidates(places)
    candidates = [_hotel_from_place(place, level=hotel.level if hotel else None) for place in ranked[:5]]
    if candidates:
        candidates[0].is_recommended = True
    for candidate in candidates[1:]:
        candidate.is_recommended = False
    return candidates


def _build_meal_candidates_near_spot(meal: MealItem, spot: SpotItem) -> list[MealItem]:
    if not _is_placeholder_meal_name(meal.name):
        return []
    if spot.latitude is None or spot.longitude is None:
        return []
    places = recommend_nearby_restaurants(longitude=spot.longitude, latitude=spot.latitude)
    places.extend(
        fetch_local_life_candidates(
            longitude=spot.longitude,
            latitude=spot.latitude,
            category="restaurant",
            radius=2000,
            page_size=10,
        )
    )
    ranked = _rank_recommendation_candidates(places)
    candidates = [_meal_from_place(place, meal_type=meal.meal_type) for place in ranked[:5]]
    if candidates:
        candidates[0].is_recommended = True
    for candidate in candidates[1:]:
        candidate.is_recommended = False
    return candidates


def _geocode_place_text(place_text: str | None, city: str | None = None) -> dict[str, Any] | None:
    """把文本地点尽量解析成带经纬度的结果。"""
    if not place_text:
        return None

    place = _pick_best_place(place_text, city=city)
    if place is not None:
        return {
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
            "address": place.get("address"),
        }

    geocode = geocode_address(place_text, city=city)
    if geocode is not None:
        return {
            "latitude": geocode.get("latitude"),
            "longitude": geocode.get("longitude"),
            "address": geocode.get("formatted_address"),
        }
    return None


def _enrich_transport(transport: TransportItem, city: str | None = None) -> bool:
    """补全单段交通的距离和耗时信息。"""
    origin = _geocode_place_text(transport.from_place, city=city)
    destination = _geocode_place_text(transport.to_place, city=city)
    if not origin or not destination:
        return False

    if origin.get("latitude") is None or origin.get("longitude") is None:
        return False
    if destination.get("latitude") is None or destination.get("longitude") is None:
        return False

    route = estimate_route(
        origin_longitude=origin["longitude"],
        origin_latitude=origin["latitude"],
        destination_longitude=destination["longitude"],
        destination_latitude=destination["latitude"],
    )
    if route is None:
        return False

    transport.distance_km = route.get("distance_km")
    transport.estimated_minutes = route.get("estimated_minutes")
    if route.get("estimated_minutes") is not None and not transport.duration:
        transport.duration = f"{route['estimated_minutes']} 分钟"
    return True


def enrich_itinerary_with_map_data(itinerary: Itinerary, city: str | None = None) -> Itinerary:
    """使用高德服务补全 itinerary 里的地图字段。"""
    enriched_count = 0

    for day in itinerary.days:
        for spot in day.spots:
            try:
                if _enrich_spot(spot, city=city or itinerary.destination):
                    enriched_count += 1
            except Exception:
                continue

        reference_spot = next(
            (
                spot
                for spot in day.spots
                if spot.latitude is not None and spot.longitude is not None
            ),
            None,
        )

        if day.hotel is not None:
            try:
                if reference_spot is not None:
                    hotel_candidates = _build_hotel_candidates_near_spot(day.hotel, reference_spot)
                    day.hotel_candidates = hotel_candidates
                    if hotel_candidates:
                        _copy_place_to_hotel(day.hotel, hotel_candidates[0].model_dump())
                        day.hotel.is_recommended = True
                        enriched_count += 1
                    elif _enrich_hotel(day.hotel, city=city or itinerary.destination):
                        day.hotel.is_recommended = True
                        enriched_count += 1
                elif _enrich_hotel(day.hotel, city=city or itinerary.destination):
                    day.hotel.is_recommended = True
                    enriched_count += 1
            except Exception:
                pass

        if reference_spot is not None:
            for meal in day.meals:
                try:
                    if meal.map_query and _enrich_meal(meal, city=city or itinerary.destination):
                        meal.is_recommended = True
                        enriched_count += 1
                        continue

                    meal_candidates = _build_meal_candidates_near_spot(meal, reference_spot)
                    day.meal_candidates.extend(meal_candidates)
                    if meal_candidates:
                        _copy_place_to_meal(meal, meal_candidates[0].model_dump())
                        meal.is_recommended = True
                        enriched_count += 1
                    elif _enrich_meal_near_spot(meal, reference_spot):
                        meal.is_recommended = True
                        enriched_count += 1
                    elif _enrich_meal(meal, city=city or itinerary.destination):
                        enriched_count += 1
                except Exception:
                    continue

        for transport in day.transport:
            try:
                if _enrich_transport(transport, city=city or itinerary.destination):
                    enriched_count += 1
            except Exception:
                continue

    if enriched_count > 0:
        note = "已补充高德地图地址、坐标、评分、参考消费、附近餐饮住宿或路线估算信息。"
        if note not in itinerary.source_notes:
            itinerary.source_notes.append(note)

    return itinerary
