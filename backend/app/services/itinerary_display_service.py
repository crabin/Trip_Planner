from __future__ import annotations

import re
from typing import Literal

from app.models.schemas import (
    DisplayBudgetItem,
    DisplayChecklistItem,
    DisplayDayCard,
    DisplayMapPoint,
    DisplayRecommendationItem,
    DisplaySection,
    DisplayTextItem,
    HotelItem,
    Itinerary,
    ItineraryDisplay,
    MealItem,
    SpotItem,
)


OVERVIEW_LABELS = [
    "日期与天数",
    "出行人",
    "出发地",
    "旅行模式与节奏",
    "推荐结构",
    "跨市交通",
    "市内交通",
    "逐晚住宿",
    "预算口径",
    "方案生成/信息核验日期",
    "关键假设",
    "待确认项",
    "确认方法",
]

PLAN_LABELS = {"推荐结构", "跨市交通", "市内交通", "逐晚住宿", "预算口径", "关键假设"}
CONFIRM_LABELS = {"待确认项", "确认方法", "方案生成/信息核验日期"}
TECHNICAL_TIP_KEYWORDS = ("LLM", "RAG", "LangChain", "Chroma", "演示", "测试", "规则", "模型", "源码")
MAX_DISPLAY_TIPS = 5
TIP_PRIORITY_KEYWORDS = (
    ("住宿", "订房", "入住", "退房", "客栈", "民宿"),
    ("返程", "车站", "机场", "航班", "车票"),
    ("天气", "雨", "风", "防滑", "薄外套"),
    ("开放", "运营", "索道", "预约"),
    ("证件", "订单", "电话", "截图"),
)


def attach_itinerary_display(itinerary: Itinerary) -> Itinerary:
    """Refresh and attach structured result-page display JSON."""
    itinerary.display = build_itinerary_display(itinerary)
    return itinerary


def build_itinerary_display(itinerary: Itinerary) -> ItineraryDisplay:
    typed_overview = {
        item.key: DisplayTextItem(
            key=item.key,
            label=item.label,
            value=item.value,
            source_path="overview_facts",
        )
        for item in itinerary.overview_facts
        if item.value
    }
    overview_fields = list(typed_overview.values()) or _parse_overview_summary(itinerary.summary)
    field_map = {item.label: item.value for item in overview_fields}
    date_range = _date_range_text(itinerary)

    if typed_overview:
        overview = [
            typed_overview.get("date_range")
            or DisplayTextItem(key="date_range", label="日期与天数", value=date_range, source_path="days"),
            typed_overview.get("travelers")
            or DisplayTextItem(key="travelers", label="出行人", value="待补充", source_path="overview_facts"),
            typed_overview.get("origin")
            or DisplayTextItem(key="origin", label="出发地", value="待补充", source_path="overview_facts"),
            typed_overview.get("pace")
            or DisplayTextItem(key="pace", label="旅行模式", value="待补充", source_path="overview_facts"),
        ]
        primary_keys = {"date_range", "travelers", "origin", "pace"}
        confirmation_keys = {"confirmations"}
        plan_highlights = [
            item
            for key, item in typed_overview.items()
            if key not in primary_keys | confirmation_keys
        ]
        confirmations = [
            item for key, item in typed_overview.items() if key in confirmation_keys
        ]
    else:
        overview = [
            DisplayTextItem(key="date_range", label="日期与天数", value=field_map.get("日期与天数", date_range), source_path="days"),
            DisplayTextItem(key="travelers", label="出行人", value=field_map.get("出行人", "待补充"), source_path="summary"),
            DisplayTextItem(key="origin", label="出发地", value=field_map.get("出发地", "待补充"), source_path="summary"),
            DisplayTextItem(key="pace", label="旅行模式", value=field_map.get("旅行模式与节奏", "待补充"), source_path="summary"),
        ]
        plan_highlights = [
            DisplayTextItem(
                key=_stable_key("plan", item.label),
                label=item.label,
                value=item.value,
                source_path="summary",
            )
            for item in overview_fields
            if item.label in PLAN_LABELS
        ]
        confirmations = [
            DisplayTextItem(
                key=_stable_key("confirm", item.label),
                label=item.label,
                value=item.value,
                source_path="summary",
            )
            for item in overview_fields
            if item.label in CONFIRM_LABELS
        ]

    budget_items = _build_budget_items(itinerary)
    day_budget_items = _build_day_budget_items(itinerary)
    map_points = _build_map_points(itinerary)
    scenic_points = [point for point in map_points if point.kind == "spot"]
    hotel_recommendations = _build_hotel_recommendations(itinerary)
    meal_recommendations = _build_meal_recommendations(itinerary)
    day_cards = _build_day_cards(itinerary)
    tips = _clean_display_tips(itinerary)
    tip_items = _build_tip_items(tips)

    sections = [
        DisplaySection(
            key="overview",
            title="行程概览",
            kind="overview",
            order=10,
            summary=itinerary.summary,
            item_keys=[item.key for item in [*overview, *plan_highlights, *confirmations]],
        ),
        DisplaySection(
            key="budget",
            title="预算明细",
            kind="budget",
            order=20,
            summary=f"总计 {_format_money(itinerary.estimated_budget)}",
            item_keys=[item.key for item in budget_items],
        ),
        DisplaySection(
            key="day_budget",
            title="按天花费",
            kind="day_budget",
            order=30,
            visible=bool(day_budget_items),
            item_keys=[item.key for item in day_budget_items],
        ),
        DisplaySection(key="editor", title="智能调整", kind="editor", order=40),
        DisplaySection(
            key="tips",
            title="旅行提示",
            kind="tips",
            order=45,
            visible=bool(tip_items),
            summary=f"{len(tip_items)} 条可勾选提示",
            item_keys=[item.key for item in tip_items],
        ),
        DisplaySection(
            key="map",
            title="景点地图",
            kind="map",
            order=50,
            visible=bool(map_points),
            summary=f"{itinerary.destination} · {len(map_points)} 个点位",
            item_keys=[item.key for item in map_points],
        ),
        DisplaySection(key="weather", title="天气信息", kind="weather", order=60),
        DisplaySection(
            key="recommendations",
            title="餐饮住宿",
            kind="recommendations",
            order=70,
            visible=bool(hotel_recommendations or meal_recommendations),
            item_keys=[item.key for item in [*hotel_recommendations, *meal_recommendations]],
        ),
        DisplaySection(
            key="poi_details",
            title="点位明细",
            kind="poi_details",
            order=80,
            visible=bool(scenic_points),
            item_keys=[item.key for item in scenic_points],
        ),
        DisplaySection(
            key="daily_plan",
            title="每日行程",
            kind="daily_plan",
            order=90,
            visible=bool(day_cards),
            item_keys=[item.key for item in day_cards],
        ),
    ]

    return ItineraryDisplay(
        title=f"{itinerary.destination}旅行计划",
        subtitle=f"{date_range} · {itinerary.destination}",
        overview=overview,
        plan_highlights=plan_highlights,
        confirmations=confirmations,
        tips=tips,
        tip_items=tip_items,
        budget_items=budget_items,
        day_budget_items=day_budget_items,
        map_points=map_points,
        scenic_points=scenic_points,
        hotel_recommendations=hotel_recommendations,
        meal_recommendations=meal_recommendations,
        day_cards=day_cards,
        sections=sections,
    )


def _parse_overview_summary(summary: str | None) -> list[DisplayTextItem]:
    normalized = re.sub(r"\s+", " ", summary or "")
    normalized = re.sub(r"^一屏概览[：:]\s*", "", normalized).strip()
    positions = []
    for label in OVERVIEW_LABELS:
        normalized_label = re.sub(r"^⚠\s*", "", label)
        for marker in (f"{label}：", f"{label}:", f"{normalized_label}：", f"{normalized_label}:"):
            index = normalized.find(marker)
            if index >= 0:
                positions.append((index, normalized_label, marker))
    positions = sorted(set(positions), key=lambda item: item[0])
    positions = [
        item
        for index, item in enumerate(positions)
        if index == 0 or item[0] != positions[index - 1][0]
    ]
    if len(positions) < 2:
        return []
    return [
        DisplayTextItem(
            key=_stable_key("overview", label),
            label=label,
            value=normalized[index + len(marker) : positions[position_index + 1][0] if position_index + 1 < len(positions) else len(normalized)].strip(),
            source_path="summary",
        )
        for position_index, (index, label, marker) in enumerate(positions)
        if normalized[index + len(marker) : positions[position_index + 1][0] if position_index + 1 < len(positions) else len(normalized)].strip()
    ]


def _build_budget_items(itinerary: Itinerary) -> list[DisplayBudgetItem]:
    budget = itinerary.budget_breakdown
    items = [
        ("tickets", "景点门票", budget.tickets, "budget_breakdown.tickets"),
        ("hotel", "酒店住宿", budget.hotel, "budget_breakdown.hotel"),
        ("meals", "餐饮费用", budget.meals, "budget_breakdown.meals"),
        ("transport", "交通费用", budget.transport, "budget_breakdown.transport"),
        ("other", "其他费用", budget.other, "budget_breakdown.other"),
    ]
    if itinerary.conversion_meta is not None:
        items = [item for item in items if item[2] > 0]
    return [
        DisplayBudgetItem(
            key=f"budget_{key}",
            label=label,
            amount=amount or 0.0,
            formatted=_format_money(amount or 0.0),
            source_path=source_path,
        )
        for key, label, amount, source_path in items
    ]


def _build_day_budget_items(itinerary: Itinerary) -> list[DisplayBudgetItem]:
    result: list[DisplayBudgetItem] = []
    for day_index, day in enumerate(itinerary.days):
        known_costs = [
            *(spot.estimated_cost for spot in day.spots),
            *(meal.estimated_cost for meal in day.meals),
            *(item.estimated_cost for item in day.transport),
            day.hotel.estimated_cost if day.hotel else None,
        ]
        if itinerary.conversion_meta is not None and not any(value is not None for value in known_costs):
            continue
        tickets = sum(spot.estimated_cost or 0.0 for spot in day.spots)
        meals = sum(meal.estimated_cost or 0.0 for meal in day.meals)
        transport = sum(item.estimated_cost or 0.0 for item in day.transport)
        hotel = (day.hotel.estimated_cost or 0.0) if day.hotel else 0.0
        total = tickets + meals + transport + hotel
        for key, label, amount in (
            ("tickets", "门票", tickets),
            ("meals", "餐饮", meals),
            ("transport", "交通", transport),
            ("hotel", "住宿", hotel),
            ("total", "当日合计", total),
        ):
            result.append(
                DisplayBudgetItem(
                    key=f"day_{day.day_index}_{key}",
                    label=f"第{day.day_index}天 · {label}",
                    amount=amount,
                    formatted=_format_money(amount),
                    source_path=f"days.{day_index}",
                )
            )
    return result


def _build_map_points(itinerary: Itinerary) -> list[DisplayMapPoint]:
    points: list[DisplayMapPoint] = []
    for day_index, day in enumerate(itinerary.days):
        for spot_index, spot in enumerate(day.spots):
            points.append(
                _map_point_from_item(
                    item=spot,
                    kind="spot",
                    label="景点",
                    key=f"spot-{day.day_index}-{spot_index}-{spot.name}",
                    day_index=day.day_index,
                    date=day.date.isoformat() if day.date else None,
                    theme=day.theme or "",
                    description=spot.description or "暂无说明",
                    recommended=False,
                    source_path=f"days.{day_index}.spots.{spot_index}",
                )
            )

        hotels = day.hotel_candidates or ([day.hotel] if day.hotel else [])
        for hotel_index, hotel in enumerate(hotels):
            points.append(
                _map_point_from_item(
                    item=hotel,
                    kind="hotel",
                    label="推荐酒店" if hotel.is_recommended else "候选酒店",
                    key=f"hotel-{day.day_index}-{hotel_index}-{hotel.name}",
                    day_index=day.day_index,
                    date=day.date.isoformat() if day.date else None,
                    theme=day.theme or "",
                    description=hotel.recommendation_reason or (f"{hotel.level}住宿" if hotel.level else "住宿候选"),
                    recommended=hotel.is_recommended,
                    source_path=f"days.{day_index}.hotel_candidates.{hotel_index}" if day.hotel_candidates else f"days.{day_index}.hotel",
                )
            )

        meals = day.meal_candidates or day.meals
        for meal_index, meal in enumerate(meals):
            points.append(
                _map_point_from_item(
                    item=meal,
                    kind="meal",
                    label=f"{'推荐' if meal.is_recommended else '候选'}{meal.meal_type or '餐饮'}",
                    key=f"meal-{day.day_index}-{meal_index}-{meal.meal_type}-{meal.name}",
                    day_index=day.day_index,
                    date=day.date.isoformat() if day.date else None,
                    theme=day.theme or "",
                    description=meal.notes or "当日推荐餐饮",
                    recommended=meal.is_recommended,
                    source_path=f"days.{day_index}.meal_candidates.{meal_index}" if day.meal_candidates else f"days.{day_index}.meals.{meal_index}",
                )
            )
    result: list[DisplayMapPoint] = []
    seen: set[tuple[object, ...]] = set()
    for point in points:
        identity = _map_point_identity(point)
        if identity is not None and identity in seen:
            continue
        if identity is not None:
            seen.add(identity)
        result.append(point)
    return result


def _map_point_from_item(
    *,
    item: SpotItem | MealItem | HotelItem,
    kind: Literal["spot", "meal", "hotel"],
    label: str,
    key: str,
    day_index: int,
    date: str | None,
    theme: str,
    description: str,
    recommended: bool,
    source_path: str,
) -> DisplayMapPoint:
    address = getattr(item, "address", None) or getattr(item, "location", None) or "待补充"
    return DisplayMapPoint(
        key=key,
        kind=kind,
        label=label,
        day_index=day_index,
        date=date,
        theme=theme,
        name=item.name,
        address=address,
        latitude=item.latitude,
        longitude=item.longitude,
        poi_id=item.poi_id,
        image_url=item.image_url,
        description=description,
        rating=item.map_rating,
        average_cost=item.map_average_cost,
        estimated_cost=item.estimated_cost,
        tags=item.map_tags or [],
        distance_meters=item.map_distance_meters,
        tel=item.map_tel,
        business_area=item.map_business_area,
        open_time_today=item.map_open_time_today,
        map_type=item.map_type,
        recommended=recommended,
        source_path=source_path,
    )


def _build_hotel_recommendations(itinerary: Itinerary) -> list[DisplayRecommendationItem]:
    result: list[DisplayRecommendationItem] = []
    seen: set[tuple[object, ...]] = set()
    for day_index, day in enumerate(itinerary.days):
        if day.hotel is None:
            continue
        identity = _item_identity(day.hotel)
        if identity is not None and identity in seen:
            continue
        if identity is not None:
            seen.add(identity)
        result.append(
            _recommendation_from_item(
                item=day.hotel,
                kind="hotel",
                key=f"hotel-recommend-{day.day_index}",
                day_index=day.day_index,
                date=day.date.isoformat() if day.date else None,
                theme=day.theme or "",
                subtitle="住宿推荐",
                note="",
                source_path=f"days.{day_index}.hotel",
            )
        )
    return result


def _build_meal_recommendations(itinerary: Itinerary) -> list[DisplayRecommendationItem]:
    result: list[DisplayRecommendationItem] = []
    seen: set[tuple[object, ...]] = set()
    for day_index, day in enumerate(itinerary.days):
        for meal_index, meal in enumerate(day.meals):
            if not (meal.is_recommended and meal.name):
                continue
            identity = _item_identity(meal)
            if identity is not None and identity in seen:
                continue
            if identity is not None:
                seen.add(identity)
            result.append(
                _recommendation_from_item(
                    item=meal,
                    kind="meal",
                    key=f"meal-recommend-{day.day_index}-{meal_index}-{meal.name}",
                    day_index=day.day_index,
                    date=day.date.isoformat() if day.date else None,
                    theme=day.theme or "",
                    subtitle=f"{meal.meal_type}推荐",
                    note=meal.notes or "",
                    source_path=f"days.{day_index}.meals.{meal_index}",
                )
            )
    return result


def _item_identity(item: MealItem | HotelItem) -> tuple[object, ...] | None:
    if item.poi_id:
        return ("poi", item.poi_id)
    if item.latitude is not None and item.longitude is not None:
        return ("coordinates", round(item.latitude, 6), round(item.longitude, 6))
    return None


def _map_point_identity(point: DisplayMapPoint) -> tuple[object, ...] | None:
    if point.poi_id:
        return (point.kind, "poi", point.poi_id)
    if point.latitude is not None and point.longitude is not None:
        return (
            point.kind,
            "coordinates",
            round(point.latitude, 6),
            round(point.longitude, 6),
        )
    return None


def _recommendation_from_item(
    *,
    item: MealItem | HotelItem,
    kind: Literal["meal", "hotel"],
    key: str,
    day_index: int,
    date: str | None,
    theme: str,
    subtitle: str,
    note: str,
    source_path: str,
) -> DisplayRecommendationItem:
    tags = [value for value in [item.ranking_label, _tag_text(item.map_tags)] if value]
    return DisplayRecommendationItem(
        key=key,
        kind=kind,
        day_index=day_index,
        date=date,
        theme=theme,
        title=item.name,
        subtitle=subtitle,
        reason=_recommendation_reason(item, kind),
        image_url=item.image_url,
        meta=_recommendation_meta(item),
        tags=tags,
        contact=" · ".join(value for value in [item.map_tel, item.address] if value),
        note=note,
        source_path=source_path,
    )


def _build_day_cards(itinerary: Itinerary) -> list[DisplayDayCard]:
    result: list[DisplayDayCard] = []
    for day_index, day in enumerate(itinerary.days):
        spot = day.spots[0] if day.spots else None
        meal = day.meals[0] if day.meals else None
        transport = day.transport[0] if day.transport else None
        fields = [
            DisplayTextItem(
                key=f"day_{day.day_index}_spot",
                label="主要景点",
                value=spot.name if spot else "未安排",
                source_path=f"days.{day_index}.spots.0.name",
            ),
            DisplayTextItem(
                key=f"day_{day.day_index}_spot_address",
                label="景点地址",
                value=(spot.address or spot.location or "待补充") if spot else "待补充",
                source_path=f"days.{day_index}.spots.0.address",
            ),
            DisplayTextItem(
                key=f"day_{day.day_index}_meal",
                label="餐饮建议",
                value=meal.name if meal else "未安排",
                source_path=f"days.{day_index}.meals.0.name",
            ),
            DisplayTextItem(
                key=f"day_{day.day_index}_hotel",
                label="住宿安排",
                value=day.hotel.name if day.hotel else "未安排",
                source_path=f"days.{day_index}.hotel.name",
            ),
            DisplayTextItem(
                key=f"day_{day.day_index}_transport",
                label="交通信息",
                value=_transport_text(transport),
                source_path=f"days.{day_index}.transport.0",
            ),
        ]
        result.append(
            DisplayDayCard(
                key=f"day_{day.day_index}",
                day_index=day.day_index,
                title=f"第{day.day_index}天 · {day.theme or '未命名主题'}",
                subtitle=_format_short_date(day.date.isoformat() if day.date else None),
                date=day.date.isoformat() if day.date else None,
                theme=day.theme or "",
                fields=fields,
                notes=day.notes,
                source_path=f"days.{day_index}",
            )
        )
    return result


def _clean_display_tips(itinerary: Itinerary) -> list[str]:
    tips = [
        tip.strip()
        for tip in itinerary.tips
        if tip.strip() and not any(keyword in tip for keyword in TECHNICAL_TIP_KEYWORDS)
    ]
    if tips:
        return _select_display_tips(tips)
    return [
        f"建议根据{itinerary.destination}当天实时天气准备雨具或薄外套。",
        "古镇、生态廊道和石板路更适合慢慢走，鞋子尽量选择舒适防滑的款式。",
    ]


def _select_display_tips(tips: list[str]) -> list[str]:
    unique_tips = list(dict.fromkeys(tips))
    ordered_tips = sorted(enumerate(unique_tips), key=lambda item: (_tip_priority(item[1]), item[0]))
    return [tip for _, tip in ordered_tips[:MAX_DISPLAY_TIPS]]


def _tip_priority(tip: str) -> int:
    for priority, keywords in enumerate(TIP_PRIORITY_KEYWORDS):
        if any(keyword in tip for keyword in keywords):
            return priority
    return len(TIP_PRIORITY_KEYWORDS)


def _build_tip_items(tips: list[str]) -> list[DisplayChecklistItem]:
    return [
        DisplayChecklistItem(
            key=f"tip_{index + 1}",
            text=tip,
            checked=False,
            source_path=f"tips.{index}",
        )
        for index, tip in enumerate(tips)
    ]


def _recommendation_reason(item: MealItem | HotelItem, kind: Literal["meal", "hotel"]) -> str:
    if item.recommendation_reason:
        return item.recommendation_reason
    reasons = []
    if item.ranking_label:
        reasons.append(item.ranking_label)
    if item.map_rating is not None:
        reasons.append(f"高德评分 {item.map_rating:.1f}")
    if item.review_count is not None:
        reasons.append(f"{item.review_count} 条评价")
    distance = _format_distance(item.map_distance_meters)
    if distance:
        reasons.append(f"距离当日景点约 {distance}")
    if item.map_tags:
        reasons.append(_tag_text(item.map_tags))
    if item.map_business_area:
        reasons.append(f"位于{item.map_business_area}商圈")
    if item.map_open_time_today:
        reasons.append(f"今日营业 {item.map_open_time_today}")
    if not reasons and item.address:
        reasons.append("已匹配真实地图地址")
    if not reasons:
        reasons.append("匹配当日餐饮预算与地点" if kind == "meal" else "匹配当日住宿预算与地点")
    return "，".join(reason for reason in reasons if reason)


def _recommendation_meta(item: MealItem | HotelItem) -> list[str]:
    source_map = {"amap": "高德", "meituan": "美团", "dianping": "大众点评"}
    values = [
        f"{item.map_rating:.1f} 分" if item.map_rating is not None else "暂无评分",
        _format_reference_cost(item.map_average_cost, item.estimated_cost),
        source_map.get(item.data_source or "", item.data_source or ""),
        f"{item.review_count} 条评价" if item.review_count is not None else "",
        _format_distance(item.map_distance_meters),
    ]
    return [value for value in values if value]


def _date_range_text(itinerary: Itinerary) -> str:
    start = itinerary.days[0].date.isoformat() if itinerary.days and itinerary.days[0].date else "待定"
    end = itinerary.days[-1].date.isoformat() if itinerary.days and itinerary.days[-1].date else "待定"
    return f"{start} 至 {end}"


def _transport_text(transport) -> str:
    if transport is None:
        return "待补充"
    if transport.distance_km is not None:
        return f"{transport.distance_km:.2f} km / {transport.estimated_minutes or 0} 分钟"
    return transport.duration or "待补充"


def _format_money(value: float | None) -> str:
    return f"¥{(value or 0.0):.0f}"


def _format_reference_cost(value: float | None, fallback: float | None) -> str:
    if value is not None:
        return f"¥{value:.0f} 参考"
    if fallback is not None and fallback > 0:
        return f"¥{fallback:.0f} 预算"
    if fallback == 0:
        return "¥0 预算"
    return "价格待查询"


def _format_distance(value: float | None) -> str:
    if value is None:
        return ""
    if value >= 1000:
        return f"{value / 1000:.1f} km"
    return f"{value:.0f} m"


def _format_short_date(value: str | None) -> str:
    if not value:
        return "待定"
    parts = value.split("-")
    if len(parts) != 3:
        return value
    return f"{parts[1]}-{parts[2]}"


def _tag_text(tags: list[str] | None) -> str:
    return " · ".join((tags or [])[:3])


def _stable_key(prefix: str, label: str) -> str:
    normalized = re.sub(r"\W+", "_", label, flags=re.UNICODE).strip("_").lower()
    return f"{prefix}_{normalized or 'item'}"
