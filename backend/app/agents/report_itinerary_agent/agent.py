from __future__ import annotations

from datetime import date as DateType, timedelta
from hashlib import sha256
import json
import re

from pydantic import ValidationError

from app.agents.report_itinerary_agent.prompts import (
    SYSTEM_PROMPT,
    build_section_extraction_user_prompt,
)
from app.agents.report_itinerary_agent.state import (
    ExtractedDay,
    ExtractedMeal,
    ExtractedReport,
    ExtractedSpot,
    ReportDayDraft,
    ReportExtractionSection,
)
from app.agents.trip_planner_agent.llms import build_chat_llm
from app.agents.trip_planner_agent.utils import extract_json_object, response_content_to_text
from app.models.schemas import (
    BudgetBreakdown,
    DayPlan,
    DeepPlanDocument,
    HotelItem,
    Itinerary,
    MealItem,
    SpotItem,
    TransportItem,
)
import app.services.report_catalog_service as report_catalog_service
from app.services.itinerary_display_service import attach_itinerary_display
from app.services.trip_service import _maybe_enrich_itinerary_with_map_data


_DAY_HEADING_PATTERN = re.compile(
    r"^#{1,4}\s*"
    r"(?:(20\d{2}-\d{2}-\d{2})(?:[（(][^）)]*[）)])?\s*)?"
    r"(?:D\s*(\d+)|Day\s*(\d+)|第\s*(\d+)\s*天)"
    r"[｜|:：\s.-]*(.*)$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_HEADING_PATTERN = re.compile(r"^#{1,4}\s+(.+)$", flags=re.MULTILINE)
_MARKDOWN_NOISE_PATTERN = re.compile(r"[*_`>#\[\]()]|!\[[^\]]*]\([^)]*\)")
_DATE_PATTERN = re.compile(r"20\d{2}-\d{2}-\d{2}")
_PRICE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*元")
_TOTAL_BUDGET_PATTERN = re.compile(r"(?:预算|总预算|预算约|预算口径)[^。\n]{0,20}?(\d{4,7})\s*元")
_OVERVIEW_STOP_PATTERN = re.compile(r"^\s*(?:---+|##\s+)", flags=re.MULTILINE)
_DAY_SECTION_STOP_PATTERN = re.compile(r"^#{1,4}\s+", flags=re.MULTILINE)
_PLACE_SPLIT_PATTERN = re.compile(r"[+/／、，,]|(?:\s+[+＋]\s+)|与|和")
_PLACE_ALIASES = {
    "天安门区域": "天安门广场",
    "天安门": "天安门广场",
    "故宫": "故宫博物院",
    "景山": "景山公园",
    "前门": "前门大街",
    "大栅栏": "大栅栏",
    "王府井": "王府井",
    "东单": "东单",
    "慕田峪": "慕田峪长城",
    "八达岭": "八达岭长城",
    "长城": "慕田峪长城",
    "颐和园": "颐和园",
    "圆明园": "圆明园",
    "什刹海": "什刹海",
    "鼓楼": "鼓楼",
    "胡同": "北京胡同",
    "南锣鼓巷": "南锣鼓巷",
}
_NON_POI_TERMS = (
    "长沙",
    "北京入住",
    "入住",
    "出发",
    "返程",
    "回长沙",
    "酒店",
    "午餐",
    "晚餐",
    "早餐",
    "美食",
    "预算",
    "成人",
    "安排",
    "适应",
    "机动",
    "补漏",
    "待确认",
    "当前",
    "旺季",
    "工作日",
    "参考",
    "规则",
    "开放",
    "选择理由",
    "高度适配",
    "老北京",
    "中轴线",
    "园林",
    "区域",
    "酒店",
    "打车",
    "包车",
)
_ACTION_SUFFIX_PATTERN = re.compile(
    r"(?:轻量适应|重点日|核心日|舒缓日|氛围日|深度美食日|散步|晚餐|小吃尝鲜|尝鲜|往返|"
    r"日组|区域|商圈|附近|重点|经典|活动|补给|休息|入住|退房).*$"
)
_LLM_CONVERSION_MARKER = "report-itinerary-conversion:llm-v1"
_FALLBACK_CONVERSION_MARKER = "report-itinerary-conversion:fallback-v1"
_EXTRACTED_REPORT_JSON_VERSION = "report-section-extraction-json-v1"


_ReportDayDraft = ReportDayDraft
_ExtractedSpot = ExtractedSpot
_ExtractedMeal = ExtractedMeal
_ExtractedDay = ExtractedDay
_ExtractedReport = ExtractedReport
_ReportExtractionSection = ReportExtractionSection


def _cache_trip_id(prefix: str, source_id: str) -> str:
    digest = sha256(source_id.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _extracted_report_json_dir():
    return report_catalog_service.REPORT_DIR / "structured_itineraries"


def _extracted_report_json_path(cache_prefix: str, source_id: str) -> str:
    return str(_extracted_report_json_dir() / f"{_cache_trip_id(cache_prefix, source_id)}.json")


def _load_extracted_report_json(cache_prefix: str, source_id: str) -> _ExtractedReport | None:
    path = _extracted_report_json_dir() / f"{_cache_trip_id(cache_prefix, source_id)}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != _EXTRACTED_REPORT_JSON_VERSION:
            return None
        if payload.get("source_id") != source_id or payload.get("cache_prefix") != cache_prefix:
            return None
        return _ExtractedReport.model_validate(payload.get("extracted_report"))
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return None


def _save_extracted_report_json(
    *,
    cache_prefix: str,
    source_id: str,
    extracted: _ExtractedReport,
    section_count: int,
) -> None:
    json_dir = _extracted_report_json_dir()
    json_dir.mkdir(parents=True, exist_ok=True)
    path = json_dir / f"{_cache_trip_id(cache_prefix, source_id)}.json"
    payload = {
        "version": _EXTRACTED_REPORT_JSON_VERSION,
        "cache_prefix": cache_prefix,
        "source_id": source_id,
        "section_count": section_count,
        "extracted_report": extracted.model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_date(value: str | None) -> DateType | None:
    if not value:
        return None
    try:
        return DateType.fromisoformat(value)
    except ValueError:
        return None


def _strip_markdown(value: str) -> str:
    value = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", value)
    value = _MARKDOWN_NOISE_PATTERN.sub("", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t-•|，,。；;：:")


def _strip_markdown_line(value: str) -> str:
    value = re.sub(r"^\s*>\s?", "", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", value)
    value = re.sub(r"^[\s\-•*\d.]+", "", value)
    return value.strip()


def _shorten_name(value: str, destination: str, max_len: int = 28) -> str | None:
    cleaned = _strip_markdown(value)
    cleaned = re.sub(r"^(?:景点|游览|餐饮|美食|午餐|晚餐|酒店|住宿|推荐|地点)\s*[：:]", "", cleaned)
    cleaned = re.split(r"[，,。；;｜|/、]", cleaned, maxsplit=1)[0].strip()
    cleaned = re.sub(r"\s*(?:约|预计|建议|可|适合|门票|人均|价格).*$", "", cleaned).strip()
    if len(cleaned) < 2:
        return None
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    if cleaned == destination:
        return None
    return cleaned


def _normalize_place_name(value: str, destination: str) -> str | None:
    cleaned = _strip_markdown(value)
    cleaned = cleaned.replace("（可选）", "").replace("(可选)", "")
    cleaned = re.sub(r"^(?:若到得早|若晚到|可二选一轻量活动|优先|备选|当天|主要景点|景点/体验)\s*[：:]?", "", cleaned)
    cleaned = _ACTION_SUFFIX_PATTERN.sub("", cleaned).strip(" ：:，,。；;/-")
    if (
        not cleaned
        or any(term in cleaned for term in _NON_POI_TERMS)
        or re.search(r"\d{1,2}[:：]\d{2}", cleaned)
    ):
        return None
    for alias, place_name in _PLACE_ALIASES.items():
        if alias in cleaned:
            return place_name
    cleaned = _shorten_name(cleaned, destination, max_len=20)
    if not cleaned or any(term in cleaned for term in _NON_POI_TERMS):
        return None
    if len(cleaned) < 2 or len(cleaned) > 20:
        return None
    return cleaned


def _unique(values: list[str], limit: int) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return tuple(result)


def _extract_total_budget(markdown: str) -> float:
    for match in _TOTAL_BUDGET_PATTERN.finditer(markdown):
        value = float(match.group(1))
        if 1000 <= value <= 1_000_000:
            return value
    return 0.0


def _extract_report_with_llm(
    *,
    markdown: str,
    destination: str,
    title: str,
    source_id: str | None = None,
    cache_prefix: str | None = None,
    force_rebuild: bool = False,
) -> _ExtractedReport | None:
    """Use the configured LLM to extract each report section into fixed JSON."""
    if source_id and cache_prefix and not force_rebuild:
        cached = _load_extracted_report_json(cache_prefix, source_id)
        if cached is not None and cached.days:
            return cached

    try:
        llm = build_chat_llm()
    except Exception:
        llm = None
    if llm is None:
        return None

    sections = _build_llm_extraction_sections(markdown, destination)
    partial_reports: list[_ExtractedReport] = []
    for section in sections:
        extracted_section = _extract_report_section_with_llm(
            llm=llm,
            section=section,
            destination=destination,
            title=title,
        )
        if extracted_section is not None:
            partial_reports.append(extracted_section)

    extracted = _merge_extracted_reports(partial_reports)
    if extracted is None or not extracted.days:
        return None
    if source_id and cache_prefix:
        try:
            _save_extracted_report_json(
                cache_prefix=cache_prefix,
                source_id=source_id,
                extracted=extracted,
                section_count=len(sections),
            )
        except OSError:
            pass
    return extracted


def _extract_report_section_with_llm(
    *,
    llm,
    section: _ReportExtractionSection,
    destination: str,
    title: str,
) -> _ExtractedReport | None:
    user_prompt = build_section_extraction_user_prompt(
        section=section,
        destination=destination,
        title=title,
    )
    try:
        response = llm.invoke([("system", SYSTEM_PROMPT), ("human", user_prompt)])
    except Exception:
        return None

    raw_text = response_content_to_text(response)
    json_text = extract_json_object(raw_text)
    if json_text is None:
        return None
    try:
        extracted = _ExtractedReport.model_validate(json.loads(json_text))
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return None
    if not extracted.days:
        if extracted.overview or extracted.total_budget > 0 or extracted.tips:
            return extracted
        return None
    return extracted


def _build_llm_extraction_sections(markdown: str, destination: str) -> list[_ReportExtractionSection]:
    sections: list[_ReportExtractionSection] = []
    daily_match = re.search(r"^##\s+每日行程\s*$", markdown, flags=re.MULTILINE)
    first_day_match = _DAY_HEADING_PATTERN.search(markdown)
    overview_end_candidates = [
        match.start()
        for match in (daily_match, first_day_match)
        if match is not None and match.start() > 0
    ]
    overview_end = min(overview_end_candidates) if overview_end_candidates else min(len(markdown), 5000)
    overview_markdown = markdown[:overview_end].strip()
    if overview_markdown:
        sections.append(
            _ReportExtractionSection(
                section_id="overview",
                section_type="overview",
                title="Report 概览",
                markdown=overview_markdown,
            )
        )

    day_matches = list(_DAY_HEADING_PATTERN.finditer(markdown))
    used_ranges: list[tuple[int, int]] = []
    for index, match in enumerate(day_matches):
        start = match.start()
        next_day_start = day_matches[index + 1].start() if index + 1 < len(day_matches) else len(markdown)
        next_major = re.search(r"^##\s+(?!每日行程).+$", markdown[match.end():next_day_start], flags=re.MULTILINE)
        end = match.end() + next_major.start() if next_major else next_day_start
        section_markdown = markdown[start:end].strip()
        if not section_markdown:
            continue
        day_index = next((group for group in match.groups()[1:4] if group), str(index + 1))
        sections.append(
            _ReportExtractionSection(
                section_id=f"day-{day_index}",
                section_type="day",
                title=_strip_markdown(match.group(0)) or f"{destination} Day {day_index}",
                markdown=section_markdown,
            )
        )
        used_ranges.append((start, end))

    for index, match in enumerate(re.finditer(r"^##\s+(.+)$", markdown, flags=re.MULTILINE), start=1):
        heading = _strip_markdown(match.group(1))
        if "每日行程" in heading:
            continue
        if any(start <= match.start() < end for start, end in used_ranges):
            continue
        next_match = re.search(r"^##\s+(.+)$", markdown[match.end():], flags=re.MULTILINE)
        end = match.end() + next_match.start() if next_match else len(markdown)
        section_markdown = markdown[match.start():end].strip()
        if section_markdown:
            sections.append(
                _ReportExtractionSection(
                    section_id=f"supplement-{index}",
                    section_type="supplement",
                    title=heading,
                    markdown=section_markdown,
                )
            )

    if not sections:
        sections.append(
            _ReportExtractionSection(
                section_id="full-report",
                section_type="full",
                title="完整 Report",
                markdown=markdown[:14000],
            )
        )
    return sections


def _merge_extracted_reports(partial_reports: list[_ExtractedReport]) -> _ExtractedReport | None:
    if not partial_reports:
        return None

    overview = next((report.overview.strip() for report in partial_reports if report.overview.strip()), "")
    total_budget = next((report.total_budget for report in partial_reports if report.total_budget > 0), 0.0)
    tips: list[str] = []
    days_by_index: dict[int, _ExtractedDay] = {}

    for report in partial_reports:
        for tip in report.tips:
            cleaned_tip = tip.strip()
            if cleaned_tip and cleaned_tip not in tips:
                tips.append(cleaned_tip)
        for day in report.days:
            existing = days_by_index.get(day.day_index)
            if existing is None:
                days_by_index[day.day_index] = day
                continue
            days_by_index[day.day_index] = _ExtractedDay(
                day_index=day.day_index,
                date=existing.date or day.date,
                theme=existing.theme or day.theme,
                full_day_text=existing.full_day_text or day.full_day_text,
                spots=[*existing.spots, *day.spots],
                meals=[*existing.meals, *day.meals],
                hotel_name=existing.hotel_name or day.hotel_name,
                hotel_query=existing.hotel_query or day.hotel_query,
                transport_note=existing.transport_note or day.transport_note,
            )

    return _ExtractedReport(
        overview=overview,
        total_budget=total_budget,
        tips=tips,
        days=sorted(days_by_index.values(), key=lambda day: day.day_index),
    )


def _build_compact_llm_source(markdown: str) -> str:
    overview = _extract_overview(markdown, "")
    daily_match = re.search(r"^##\s+每日行程\s*$", markdown, flags=re.MULTILINE)
    if not daily_match:
        return markdown[:12000]

    tail = markdown[daily_match.start():]
    next_section = re.search(r"^##\s+(?!每日行程).+$", tail[daily_match.end() - daily_match.start():], flags=re.MULTILINE)
    daily_section = tail[: daily_match.end() - daily_match.start() + next_section.start()] if next_section else tail
    return f"{overview}\n\n{daily_section[:14000]}"


def _extract_overview(markdown: str, title: str) -> str:
    start = markdown.find("> 一屏概览")
    if start < 0:
        start = markdown.find("一屏概览")
    if start < 0:
        heading_match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
        return heading_match.group(1).strip() if heading_match else title

    tail = markdown[start:]
    stop_match = _OVERVIEW_STOP_PATTERN.search(tail)
    overview = tail[: stop_match.start()] if stop_match else tail[:2000]
    lines = [
        _strip_markdown_line(line)
        for line in overview.splitlines()
        if _strip_markdown_line(line)
    ]
    return "\n".join(lines).strip() or title


def _extract_section_text(body: str, heading_keywords: tuple[str, ...]) -> str:
    lines = body.splitlines()
    capture = False
    captured: list[str] = []
    for line in lines:
        stripped = line.strip()
        heading = _strip_markdown(stripped)
        is_heading = stripped.startswith("#") or re.match(r"^[-*]\s*(?:\*\*)?[^：:]{2,24}(?:\*\*)?$", stripped)
        if is_heading:
            if capture:
                break
            capture = any(keyword in heading for keyword in heading_keywords)
            continue
        if capture:
            captured.append(line)
    return "\n".join(captured).strip()


def _extract_day_narrative(body: str, max_chars: int = 1500) -> str:
    lines: list[str] = []
    for raw_line in body.splitlines():
        stripped = _strip_markdown_line(raw_line)
        if not stripped:
            continue
        if stripped in {"景点/体验", "午晚餐或商圈", "当日住宿与回程", "机动时间、体力节奏、备选"}:
            lines.append(f"【{stripped}】")
        else:
            lines.append(stripped)
    narrative = "\n".join(lines)
    return narrative[:max_chars].rstrip()


def _extract_candidates_from_text(text: str, destination: str, limit: int) -> tuple[str, ...]:
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = _strip_markdown_line(raw_line)
        if not line:
            continue
        for part in _PLACE_SPLIT_PATTERN.split(line):
            name = _normalize_place_name(part, destination)
            if name:
                candidates.append(name)
    return _unique(candidates, limit)


def _extract_structured_place_names(text: str, destination: str, limit: int) -> tuple[str, ...]:
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = re.search(r"(?:^\d+\.\s*|^[-*]\s*)\*\*(.+?)\*\*", line)
        if not match:
            continue
        title = re.sub(r"[（(].*?[）)]", "", match.group(1)).strip()
        for part in _PLACE_SPLIT_PATTERN.split(title):
            name = _normalize_place_name(part, destination)
            if name:
                candidates.append(name)
    return _unique(candidates, limit)


def _extract_spot_names(title: str, body: str, destination: str, limit: int = 3) -> tuple[str, ...]:
    title_candidates = list(_extract_candidates_from_text(title, destination, limit=6))
    experience_section = _extract_section_text(body, ("景点", "体验"))
    structured_candidates = list(_extract_structured_place_names(experience_section, destination, limit=limit))
    body_candidates = list(_extract_candidates_from_text(experience_section or body, destination, limit=10))

    # 首日轻量适应常出现“前门/王府井”备选。优先用用户报告中更明确的王府井商圈，
    # 避免把“前门晚餐/酒店入住”等泛化词误当成主景点。
    if "王府井" in title + body and ("轻量" in title or "首日" in body):
        return ("王府井",)

    return _unique([*structured_candidates, *title_candidates, *body_candidates], limit)


def _extract_meal_names(body: str, destination: str, limit: int = 2) -> tuple[str, ...]:
    meal_section = _extract_section_text(body, ("餐", "美食", "商圈"))
    candidates: list[str] = []
    for raw_line in (meal_section or body).splitlines():
        line = _strip_markdown_line(raw_line)
        if (
            not line
            or "→" in line
            or "回酒店" in line
            or line in {"午晚餐或商圈", "时间—地点链"}
            or "选择理由" in line
            or not any(keyword in line for keyword in ("餐", "吃", "美食", "小吃", "烤鸭", "涮肉", "京味"))
        ):
            continue
        if "王府井" in line:
            candidates.append("王府井附近京味菜")
        elif "前门" in line or "大栅栏" in line:
            candidates.append("前门大栅栏附近京味菜")
        elif "什刹海" in line or "鼓楼" in line:
            candidates.append("什刹海鼓楼附近小吃")
        elif "烤鸭" in line:
            candidates.append("北京烤鸭")
        elif "涮肉" in line:
            candidates.append("北京铜锅涮肉")
        elif "午餐" in line or "晚餐" in line:
            continue
        else:
            shortened = _shorten_name(line, destination, max_len=24)
            if shortened and "成人" not in shortened and "预算" not in shortened and len(shortened) > 2:
                candidates.append(shortened)
    return _unique(candidates, limit)


def _extract_hotel_name(markdown: str, destination: str) -> str:
    overview = _extract_overview(markdown, "")
    if "东城核心区" in overview:
        return f"{destination}东城核心区酒店"
    for area in ("前门", "崇文门", "东单", "王府井", "东直门", "雍和宫"):
        if area in overview:
            return f"{area}附近酒店"
    return f"{destination}核心区酒店"


def _extract_names_from_lines(
    body: str,
    destination: str,
    keywords: tuple[str, ...],
    limit: int,
) -> tuple[str, ...]:
    names: list[str] = []
    for raw_line in body.splitlines():
        line = _strip_markdown(raw_line)
        if not line or not any(keyword in line for keyword in keywords):
            continue
        after_label = re.split(r"[：:]", line, maxsplit=1)
        candidates = [after_label[-1], line]
        for candidate in candidates:
            name = _shorten_name(candidate, destination)
            if name:
                names.append(name)
    return _unique(names, limit)


def _fallback_headings(markdown: str, destination: str, limit: int) -> tuple[str, ...]:
    headings: list[str] = []
    for heading in _HEADING_PATTERN.findall(markdown):
        cleaned = _shorten_name(heading, destination)
        if cleaned and not any(term in cleaned for term in ("攻略", "预算", "交通", "来源", "目录")):
            headings.append(cleaned)
    return _unique(headings, limit)


def _split_day_sections(markdown: str, destination: str) -> list[_ReportDayDraft]:
    matches = list(_DAY_HEADING_PATTERN.finditer(markdown))
    if not matches:
        spot_names = _extract_names_from_lines(
            markdown,
            destination,
            ("景点", "游览", "打卡", "博物馆", "公园", "古城", "海", "寺", "山"),
            8,
        ) or _fallback_headings(markdown, destination, 8)
        meal_names = _extract_names_from_lines(markdown, destination, ("餐", "美食", "小吃", "咖啡"), 8)
        hotel_names = _extract_names_from_lines(markdown, destination, ("酒店", "住宿", "民宿"), 1)
        day_count = max(1, min(5, len(spot_names) or 1))
        return [
            _ReportDayDraft(
                day_index=index + 1,
                date=None,
                theme=f"{destination}深度攻略 Day {index + 1}",
                body=markdown,
                spot_names=tuple(spot_names[index : index + 1]),
                meal_names=tuple(meal_names[index : index + 1]),
                hotel_name=hotel_names[0] if hotel_names else None,
            )
            for index in range(day_count)
        ]

    drafts: list[_ReportDayDraft] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        groups = match.groups()
        date_value = _parse_date(groups[0]) if groups[0] else None
        day_index = int(next(group for group in groups[1:4] if group) or index + 1)
        title_suffix = _strip_markdown(groups[4] or "")
        body = markdown[start:end]
        spot_names = _extract_spot_names(title_suffix, body, destination)
        meal_names = _extract_meal_names(body, destination)
        hotel_names = _extract_names_from_lines(body, destination, ("酒店", "住宿", "民宿"), 1)
        drafts.append(
            _ReportDayDraft(
                day_index=day_index,
                date=date_value,
                theme=title_suffix or f"{destination}深度攻略 Day {day_index}",
                body=body,
                spot_names=spot_names,
                meal_names=meal_names,
                hotel_name=hotel_names[0] if hotel_names else None,
            )
        )
    return sorted(drafts, key=lambda item: item.day_index)


def _estimate_cost(text: str, default: float | None = None) -> float | None:
    match = _PRICE_PATTERN.search(text)
    if match:
        return float(match.group(1))
    if "免费" in text:
        return 0.0
    return default


def _apply_report_budget(itinerary: Itinerary, report_budget: float) -> Itinerary:
    if report_budget > 0:
        itinerary.estimated_budget = report_budget
        itinerary.budget_breakdown = BudgetBreakdown(other=report_budget, total=report_budget)
    else:
        itinerary.estimated_budget = 0.0
        itinerary.budget_breakdown = BudgetBreakdown()
    return itinerary


def _itinerary_from_extracted_report(
    *,
    source_id: str,
    extracted: _ExtractedReport,
    destination: str,
    fallback_start_date: DateType,
    fallback_day_texts: dict[int, str] | None = None,
    title: str,
    cache_prefix: str,
) -> Itinerary:
    report_budget = extracted.total_budget
    default_hotel_name = next(
        (day.hotel_name for day in extracted.days if day.hotel_name),
        _extract_hotel_name(extracted.overview, destination),
    )
    days: list[DayPlan] = []
    fallback_day_texts = fallback_day_texts or {}
    for index, extracted_day in enumerate(sorted(extracted.days, key=lambda day: day.day_index)):
        current_date = _parse_date(extracted_day.date) or (fallback_start_date + timedelta(days=index))
        full_day_text = extracted_day.full_day_text.strip() or fallback_day_texts.get(extracted_day.day_index, "")
        spots = [
            SpotItem(
                name=spot.name.strip(),
                start_time=f"{10 + spot_index * 2:02d}:00",
                end_time=f"{12 + spot_index * 2:02d}:00",
                description=spot.description.strip() or full_day_text[:280],
                estimated_cost=None,
                location=spot.map_query.strip() or f"{destination} {spot.name.strip()}",
                map_query=spot.map_query.strip() or f"{destination} {spot.name.strip()}",
            )
            for spot_index, spot in enumerate(extracted_day.spots[:4])
            if spot.name.strip()
        ]
        if not spots:
            spots = [
                SpotItem(
                    name=destination,
                    description=full_day_text[:280] or extracted_day.theme,
                    estimated_cost=None,
                    location=destination,
                )
            ]
        meals = [
            MealItem(
                name=meal.name.strip(),
                meal_type=meal.meal_type.strip() or "餐饮",
                estimated_cost=0.0,
                notes=meal.notes.strip(),
                map_query=meal.map_query.strip() or f"{destination} {meal.name.strip()}",
                data_source="destination_intelligence_report",
            )
            for meal in extracted_day.meals[:3]
            if meal.name.strip()
        ]
        hotel_name = extracted_day.hotel_name.strip() or default_hotel_name
        days.append(
            DayPlan(
                day_index=index + 1,
                date=current_date,
                theme=extracted_day.theme.strip() or f"{destination} Day {index + 1}",
                spots=spots,
                meals=meals,
                hotel=HotelItem(
                    name=hotel_name,
                    level="报告建议住宿区域",
                    estimated_cost=0.0,
                    location=extracted_day.hotel_query.strip() or hotel_name,
                    map_query=extracted_day.hotel_query.strip() or f"{destination} {hotel_name}",
                    data_source="destination_intelligence_report",
                ),
                transport=[
                    TransportItem(
                        mode="市内交通",
                        from_place=hotel_name,
                        to_place=spots[-1].name,
                        estimated_cost=0.0,
                        duration=extracted_day.transport_note.strip()
                        or "以 Report 的时间—地点链为准",
                    )
                ],
                notes=[full_day_text or extracted_day.theme],
            )
        )

    itinerary = Itinerary(
        trip_id=_cache_trip_id(cache_prefix, source_id),
        destination=destination,
        summary=extracted.overview.strip() or title,
        days=days,
        estimated_budget=report_budget,
        budget_breakdown=BudgetBreakdown(other=report_budget, total=report_budget) if report_budget else BudgetBreakdown(),
        tips=extracted.tips
        or [
            "按 Report 的待确认清单复核关键预订、交通班次、酒店规则和景区预约。",
            "每日路线以 Report 的时间—地点链为准；地图点位用于辅助确认空间分布。",
        ],
        source_notes=[
            "结果页由 Destination Intelligence Report 转换生成。",
            _LLM_CONVERSION_MARKER,
            f"Structured JSON: {_extracted_report_json_path(cache_prefix, source_id)}",
            f"Report/Deep source id: {source_id}",
        ],
    )
    itinerary = _maybe_enrich_itinerary_with_map_data(itinerary, city=destination)
    return attach_itinerary_display(_apply_report_budget(itinerary, report_budget))


def _needs_rebuild_from_cache(itinerary: Itinerary) -> bool:
    joined_text = "\n".join(
        [
            itinerary.summary,
            *itinerary.tips,
            *itinerary.source_notes,
            *(
                note
                for day in itinerary.days
                for note in day.notes
            ),
            *(
                spot.description or ""
                for day in itinerary.days
                for spot in day.spots
            ),
            *(
                meal.notes or ""
                for day in itinerary.days
                for meal in day.meals
            ),
        ]
    )
    if "根据深度规划 Report 提取" in joined_text or itinerary.summary.startswith("根据《"):
        return True
    if _LLM_CONVERSION_MARKER in itinerary.source_notes:
        return False
    if _FALLBACK_CONVERSION_MARKER in itinerary.source_notes and build_chat_llm() is None:
        return False
    return True


def _document_to_itinerary(
    *,
    source_id: str,
    document: DeepPlanDocument,
    destination: str,
    start_date: DateType | None,
    end_date: DateType | None,
    title: str,
    cache_prefix: str,
    force_rebuild: bool = False,
) -> Itinerary:
    if start_date is None:
        dates = [_parse_date(value) for value in _DATE_PATTERN.findall(document.markdown)]
        start_date = next((value for value in dates if value is not None), None)
    if start_date is None:
        start_date = DateType.today()

    drafts_for_text = _split_day_sections(document.markdown, destination)
    fallback_day_texts = {
        draft.day_index: _extract_day_narrative(draft.body)
        for draft in drafts_for_text
    }
    extracted = _extract_report_with_llm(
        markdown=document.markdown,
        destination=destination,
        title=title,
        source_id=source_id,
        cache_prefix=cache_prefix,
        force_rebuild=force_rebuild,
    )
    if extracted is not None:
        try:
            _save_extracted_report_json(
                cache_prefix=cache_prefix,
                source_id=source_id,
                extracted=extracted,
                section_count=len(_build_llm_extraction_sections(document.markdown, destination)),
            )
        except OSError:
            pass
        return _itinerary_from_extracted_report(
            source_id=source_id,
            extracted=extracted,
            destination=destination,
            fallback_start_date=start_date,
            fallback_day_texts=fallback_day_texts,
            title=title,
            cache_prefix=cache_prefix,
        )

    drafts = drafts_for_text
    overview = _extract_overview(document.markdown, title)
    report_budget = _extract_total_budget(overview + "\n" + document.markdown[:3000])

    if end_date is not None:
        day_count = max((end_date - start_date).days + 1, 1)
    else:
        day_count = max(len(drafts), 1)
    if len(drafts) < day_count:
        drafts.extend(
            _ReportDayDraft(
                day_index=index + 1,
                date=None,
                theme=f"{destination}深度攻略 Day {index + 1}",
                body=document.markdown,
                spot_names=(),
                meal_names=(),
                hotel_name=None,
            )
            for index in range(len(drafts), day_count)
        )
    drafts = drafts[:day_count]

    default_hotel_name = next((draft.hotel_name for draft in drafts if draft.hotel_name), None)
    report_hotel_name = default_hotel_name or _extract_hotel_name(document.markdown, destination)
    days: list[DayPlan] = []
    for index, draft in enumerate(drafts):
        current_date = draft.date or (start_date + timedelta(days=index))
        spot_names = draft.spot_names or (destination,)
        meal_names = draft.meal_names
        narrative = _extract_day_narrative(draft.body)
        spots = [
            SpotItem(
                name=name,
                start_time=f"{10 + spot_index * 2:02d}:00",
                end_time=f"{12 + spot_index * 2:02d}:00",
                description=narrative[:280] if narrative else draft.theme,
                estimated_cost=None,
                location=destination,
                map_query=f"{destination} {name}",
                data_source="destination_intelligence_report",
            )
            for spot_index, name in enumerate(spot_names[:3])
        ]
        meals = [
            MealItem(
                name=name,
                meal_type="午餐" if meal_index == 0 else "晚餐",
                estimated_cost=0.0,
                notes=_extract_day_narrative(_extract_section_text(draft.body, ("餐", "美食", "商圈")), 320),
                map_query=f"{destination} {name}",
                data_source="destination_intelligence_report",
            )
            for meal_index, name in enumerate(meal_names[:2])
        ]
        hotel_name = draft.hotel_name or report_hotel_name
        days.append(
            DayPlan(
                day_index=index + 1,
                date=current_date,
                theme=draft.theme,
                spots=spots,
                meals=meals,
                hotel=HotelItem(
                    name=hotel_name,
                    level="报告建议住宿区域",
                    estimated_cost=0.0,
                    location="前门/崇文门/东单/王府井" if destination == "北京" else f"{destination}核心区",
                    map_query=f"{destination} {hotel_name}",
                    data_source="destination_intelligence_report",
                ),
                transport=[
                    TransportItem(
                        mode="市内交通",
                        from_place=hotel_name,
                        to_place=spots[-1].name if spots else destination,
                        estimated_cost=0.0,
                        duration="地铁为主，打车补位；以报告当日时间—地点链为准",
                    )
                ],
                notes=[
                    narrative or draft.theme,
                ],
            )
        )

    source_notes = [
        "结果页由 Destination Intelligence Report 转换生成。",
        _FALLBACK_CONVERSION_MARKER,
        f"Report/Deep source id: {source_id}",
    ]
    source_notes.extend(
        f"{source.section_title or '研究来源'}：{source.title or source.query}"
        for source in document.sources[:3]
        if source.title or source.query
    )
    itinerary = Itinerary(
        trip_id=_cache_trip_id(cache_prefix, source_id),
        destination=destination,
        summary=overview,
        days=days,
        estimated_budget=report_budget,
        budget_breakdown=BudgetBreakdown(other=report_budget, total=report_budget) if report_budget else BudgetBreakdown(),
        tips=[
            "按 Report 的待确认清单复核往返班次、预算口径、长城选择、天安门参观方式和酒店规则。",
            "每日路线以 Report 的时间—地点链为准；地图点位用于辅助确认空间分布。",
        ],
        source_notes=source_notes,
    )
    itinerary = _maybe_enrich_itinerary_with_map_data(itinerary, city=destination)
    return attach_itinerary_display(_apply_report_budget(itinerary, report_budget))


class ReportItineraryAgent:
    """Convert a Destination Intelligence Report document into result-page JSON."""

    def convert_document_to_itinerary(
        self,
        *,
        source_id: str,
        document: DeepPlanDocument,
        destination: str,
        start_date: DateType | None,
        end_date: DateType | None,
        title: str,
        cache_prefix: str,
        force_rebuild: bool = False,
    ) -> Itinerary:
        return _document_to_itinerary(
            source_id=source_id,
            document=document,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            title=title,
            cache_prefix=cache_prefix,
            force_rebuild=force_rebuild,
        )


def convert_document_to_itinerary(
    *,
    source_id: str,
    document: DeepPlanDocument,
    destination: str,
    start_date: DateType | None,
    end_date: DateType | None,
    title: str,
    cache_prefix: str,
    force_rebuild: bool = False,
) -> Itinerary:
    """Module-level convenience wrapper used by service code and tests."""
    return ReportItineraryAgent().convert_document_to_itinerary(
        source_id=source_id,
        document=document,
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        title=title,
        cache_prefix=cache_prefix,
        force_rebuild=force_rebuild,
    )


__all__ = [
    "ReportItineraryAgent",
    "convert_document_to_itinerary",
    "_ExtractedDay",
    "_ExtractedMeal",
    "_ExtractedReport",
    "_ExtractedSpot",
    "_build_llm_extraction_sections",
    "_cache_trip_id",
    "_document_to_itinerary",
    "_extract_report_section_with_llm",
    "_extract_report_with_llm",
    "_extracted_report_json_path",
    "_load_extracted_report_json",
    "_maybe_enrich_itinerary_with_map_data",
    "_needs_rebuild_from_cache",
    "_parse_date",
    "_save_extracted_report_json",
]
