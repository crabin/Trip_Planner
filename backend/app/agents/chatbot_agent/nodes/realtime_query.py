from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
import json
import re
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.trip_planner_agent.utils import extract_json_object, response_content_to_text
from app.integrations.web_search import FallbackWebSearchAgency, TavilyResponse
from app.models.schemas import (
    ChatbotMessageRequest,
    ChatbotMessageResponse,
    ChatbotResearchStep,
    ChatbotSearchSource,
)
from app.services.weather_service import get_weather_forecast

from ..prompts import REALTIME_QUERY_ROUTER_SYSTEM_PROMPT
from ..state import IntentDecision
from ..utils import MAX_SEARCH_RESULTS, format_search_sources

RealtimeQueryKind = Literal[
    "weather",
    "scenic_notice",
    "transport",
    "ticket",
    "business_hours",
    "generic_search",
]

WEATHER_DATE_OFFSETS = {
    "今天": 0,
    "明天": 1,
    "后天": 2,
}
WEATHER_NOISE_WORDS = (
    "天气",
    "预报",
    "查询",
    "查",
    "帮我",
    "一下",
    "的",
    "吗",
    "？",
    "?",
)


@dataclass(frozen=True)
class RealtimeQueryResult:
    response: ChatbotMessageResponse
    steps: list[ChatbotResearchStep]


@dataclass(frozen=True)
class RealtimeRouteDecision:
    query_kind: RealtimeQueryKind
    search_query: str
    reason: str


class RealtimeGraphState(TypedDict, total=False):
    request: ChatbotMessageRequest
    intent_decision: IntentDecision
    route: RealtimeRouteDecision
    steps: list[ChatbotResearchStep]
    response: ChatbotMessageResponse
    events: list[dict[str, Any]]


class RealtimeQueryRouter:
    def __init__(self, *, llm: Any | None = None, search_agency: FallbackWebSearchAgency) -> None:
        self.llm = llm
        self.search_agency = search_agency
        self.graph = self._build_graph()

    def run(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> RealtimeQueryResult:
        final_response: ChatbotMessageResponse | None = None
        steps: list[ChatbotResearchStep] = []
        for event in self.stream(request, decision):
            if event["event"] == "query_plan":
                steps = event["data"]
            if event["event"] == "query_step":
                steps = _upsert_step(steps, event["data"])
            if event["event"] == "final":
                final_response = event["data"]
        if final_response is None:
            raise RuntimeError("Realtime query stream finished without a final response.")
        return RealtimeQueryResult(response=final_response, steps=steps)

    def stream(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> Iterator[dict[str, Any]]:
        result = self.graph.invoke(
            {
                "request": request,
                "intent_decision": decision,
                "events": [],
            }
        )
        yield from result.get("events", [])

    def _build_graph(self):
        graph = StateGraph(RealtimeGraphState)
        graph.add_node("route_query", self._route_query)
        graph.add_node("execute_query", self._execute_query)
        graph.set_entry_point("route_query")
        graph.add_edge("route_query", "execute_query")
        graph.add_edge("execute_query", END)
        return graph.compile()

    def _route_query(self, state: RealtimeGraphState) -> RealtimeGraphState:
        request = state["request"]
        decision = state["intent_decision"]
        route = self._classify_with_llm(request, decision)
        kind = route.query_kind
        query = build_query(route.search_query, decision, kind)
        steps = [
            ChatbotResearchStep(
                id="classify",
                title="识别实时查询类型",
                status="completed",
                summary=f"已识别为：{query_kind_label(kind)}。{route.reason}",
                sources=[],
            ),
            ChatbotResearchStep(
                id="query",
                title=handler_title(kind),
                status="pending",
                query=query,
                summary="",
                sources=[],
            ),
        ]
        return {
            "route": route,
            "steps": steps,
            "events": [{"event": "query_plan", "data": steps}],
        }

    def _execute_query(self, state: RealtimeGraphState) -> RealtimeGraphState:
        request = state["request"]
        decision = state["intent_decision"]
        route = state["route"]
        kind = route.query_kind
        steps = state["steps"]
        running_step = steps[1].model_copy(update={"status": "running"})
        events = [*state.get("events", []), {"event": "query_step", "data": running_step}]

        try:
            if kind == "weather":
                answer, sources = answer_weather(route.search_query or request.message)
            else:
                search_response = self.search_agency.basic_search_news(
                    running_step.query or route.search_query,
                    max_results=MAX_SEARCH_RESULTS,
                )
                sources = format_search_sources(search_response)
                answer = answer_from_search(
                    question=request.message,
                    query_kind=kind,
                    response=search_response,
                    sources=sources,
                )
            completed_step = running_step.model_copy(
                update={
                    "status": "completed",
                    "summary": summarize_step(kind, sources, answer),
                    "sources": sources,
                }
            )
            events.append({"event": "query_step", "data": completed_step})
            final_steps = [steps[0], completed_step]
            response = ChatbotMessageResponse(
                intent="search",
                reply=answer,
                reason=decision.reason,
                sources=sources,
                research_steps=final_steps,
            )
            events.append(
                {
                    "event": "final",
                    "data": response,
                }
            )
            return {
                "steps": final_steps,
                "response": response,
                "events": events,
            }
        except Exception as exc:
            failed_step = running_step.model_copy(
                update={
                    "status": "failed",
                    "summary": f"该项暂时无法查证：{exc}",
                    "sources": [],
                }
            )
            events.append({"event": "query_step", "data": failed_step})
            final_steps = [steps[0], failed_step]
            response = ChatbotMessageResponse(
                intent="search",
                reply=(
                    "## 明确结论\n"
                    "暂时无法确认这条实时信息。\n\n"
                    "## 需要再次确认\n"
                    f"- 原因：{exc}\n"
                    "- 建议稍后重试，或直接查看官方渠道。"
                ),
                reason=decision.reason,
                research_steps=final_steps,
            )
            events.append(
                {
                    "event": "final",
                    "data": response,
                }
            )
            return {
                "steps": final_steps,
                "response": response,
                "events": events,
            }

    def _classify_with_llm(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> RealtimeRouteDecision:
        fallback_query = decision.search_query or request.message
        if self.llm is None:
            return RealtimeRouteDecision(
                query_kind="generic_search",
                search_query=fallback_query,
                reason="LLM 实时路由不可用，使用通用实时查询。",
            )
        try:
            response = self.llm.invoke(
                [
                    ("system", REALTIME_QUERY_ROUTER_SYSTEM_PROMPT),
                    (
                        "human",
                        json.dumps(
                            {
                                "message": request.message,
                                "intent_search_query": decision.search_query,
                                "itinerary_destination": (
                                    request.current_itinerary.destination
                                    if request.current_itinerary is not None
                                    else None
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ]
            )
            raw_text = response_content_to_text(response)
            json_text = extract_json_object(raw_text)
            if json_text is None:
                raise ValueError("LLM 未返回 JSON")
            payload = json.loads(json_text)
            kind = payload.get("query_kind")
            if kind not in RealtimeQueryKind.__args__:
                raise ValueError(f"未知实时查询类型: {kind}")
            search_query = str(payload.get("search_query") or fallback_query).strip()
            return RealtimeRouteDecision(
                query_kind=kind,
                search_query=search_query or fallback_query,
                reason=str(payload.get("reason") or ""),
            )
        except Exception:
            return RealtimeRouteDecision(
                query_kind="generic_search",
                search_query=fallback_query,
                reason="LLM 实时路由失败，使用通用实时查询。",
            )


def classify_realtime_query(message: str) -> RealtimeQueryKind:
    return "generic_search"


def build_query(message: str, decision: IntentDecision, kind: RealtimeQueryKind) -> str:
    base = message
    templates = {
        "weather": "",
        "scenic_notice": "官方 公告 开放 闭园 施工 预约",
        "transport": "航班 飞机 高铁 火车 航司 12306 需要多久",
        "ticket": "官方 门票 预约 票价",
        "business_hours": "官方 开放时间 营业时间 今日",
        "generic_search": "",
    }
    suffix = templates[kind]
    return f"{base} {suffix}".strip()


def query_kind_label(kind: RealtimeQueryKind) -> str:
    return {
        "weather": "天气查询",
        "scenic_notice": "景区公告查询",
        "transport": "交通查询",
        "ticket": "门票查询",
        "business_hours": "营业时间查询",
        "generic_search": "通用实时查询",
    }[kind]


def handler_title(kind: RealtimeQueryKind) -> str:
    return {
        "weather": "调用天气服务",
        "scenic_notice": "查询景区官方公告",
        "transport": "查询交通实时信息",
        "ticket": "查询门票和预约信息",
        "business_hours": "查询开放或营业时间",
        "generic_search": "查询实时网页信息",
    }[kind]


def answer_weather(message: str) -> tuple[str, list[ChatbotSearchSource]]:
    city = extract_weather_city(message)
    if not city:
        raise RuntimeError("未能识别天气查询的城市。")

    forecast = get_weather_forecast(city)
    target_label, target_day = select_weather_day(message, forecast)
    if target_day is None:
        raise RuntimeError("天气服务没有返回可用的逐日预报。")

    city_name = forecast.get("city") or city
    date_text = target_day.get("date") or "日期未返回"
    day_weather = target_day.get("day_weather") or "未知"
    night_weather = target_day.get("night_weather") or "未知"
    day_temp = target_day.get("day_temp")
    night_temp = target_day.get("night_temp")
    day_wind = target_day.get("day_wind")
    night_wind = target_day.get("night_wind")
    report_time = forecast.get("report_time") or "未返回"

    temp_line = "温度暂未返回"
    if day_temp or night_temp:
        temp_line = f"{night_temp or '?'}~{day_temp or '?'}℃"

    wind_parts = []
    if day_wind:
        wind_parts.append(f"白天{day_wind}风")
    if night_wind and night_wind != day_wind:
        wind_parts.append(f"夜间{night_wind}风")
    wind_line = "，".join(wind_parts) if wind_parts else "风向暂未返回"

    answer = "\n".join(
        [
            "## 明确结论",
            f"{city_name}{target_label}天气：白天{day_weather}，夜间{night_weather}，温度{temp_line}。",
            "",
            "## 关键数据",
            f"- 日期：{date_text}",
            f"- 风向：{wind_line}",
            f"- 预报发布时间：{report_time}",
            "",
            "## 注意事项",
            f"- {build_weather_tip(day_weather, night_weather)}",
            "- 天气变化快，出发前建议再看一次临近预报。",
        ]
    )
    return answer, []


def answer_from_search(
    *,
    question: str,
    query_kind: RealtimeQueryKind,
    response: TavilyResponse,
    sources: list[ChatbotSearchSource],
) -> str:
    if not response.results:
        return (
            "## 明确结论\n"
            "没有找到足够可靠的实时结果。\n\n"
            "## 需要再次确认\n"
            "- 建议换一个更具体的景点、日期或交通方式再查。\n"
            "- 如涉及购票、开放时间或交通班次，请以官方渠道为准。"
        )

    first = response.results[0]
    content = first.content.strip() or "搜索结果未提供摘要。"
    if len(content) > 180:
        content = f"{content[:180]}..."
    has_official_source = has_reliable_source(sources)
    caution = {
        "scenic_notice": "景区开放、闭园、施工和预约变化较快，请以景区官方公告为准。",
        "transport": "交通耗时和班次变化较快，航班以航司为准，铁路以12306为准。",
        "ticket": "门票价格和优惠政策可能调整，请以景区官方购票页为准。",
        "business_hours": "营业时间可能受天气、节假日或活动影响，请以官方当天信息为准。",
        "generic_search": "实时信息可能变化，建议出发前再次确认。",
        "weather": "天气变化快，建议出发前再次确认。",
    }[query_kind]
    source_lines = [
        f"- [{source.title or '来源'}]({source.url})"
        for source in sources[:3]
        if source.url
    ]
    if not source_lines:
        source_lines = ["- 搜索结果未返回可点击来源。"]

    conclusion_title = "## 明确结论" if has_official_source else "## 当前线索"
    conclusion_text = (
        f"针对“{question}”，当前查到的主要线索是：{content}"
        if has_official_source
        else f"针对“{question}”，目前只查到非官方或待核实线索，暂时不足以确认：{content}"
    )

    return "\n".join(
        [
            conclusion_title,
            conclusion_text,
            "",
            "## 来源",
            *source_lines,
            "",
            "## 注意事项",
            f"- {caution}",
        ]
    )


def has_reliable_source(sources: list[ChatbotSearchSource]) -> bool:
    official_terms = ("官方", "公告", "官网", "12306", "航司", "机场", "政府", "文旅")
    official_domains = (".gov.", "12306.cn")
    for source in sources:
        title = source.title or ""
        url = source.url or ""
        if any(term in title for term in official_terms):
            return True
        if any(domain in url for domain in official_domains):
            return True
    return False


def summarize_step(
    kind: RealtimeQueryKind,
    sources: list[ChatbotSearchSource],
    answer: str,
) -> str:
    if kind == "weather":
        return "已获取天气服务返回的结构化预报。"
    if sources:
        return f"已获取 {len(sources)} 条实时搜索来源。"
    if "没有找到足够可靠" in answer:
        return "没有找到足够可靠的实时结果。"
    return "已完成实时查询。"


def extract_weather_city(message: str) -> str | None:
    explicit_match = re.search(
        r"([\u4e00-\u9fff]{2,8}?)(?:市)?(?:今天|明天|后天|天气|气温|降雨|下雨|会下雨|预报)",
        message,
    )
    if explicit_match:
        city = explicit_match.group(1)
        city = re.sub(r"^(帮我|查询|查一下|查|看一下|看看)", "", city)
        for word in WEATHER_DATE_OFFSETS:
            city = city.replace(word, "")
        if city:
            return city

    text = message.strip()
    for word in WEATHER_DATE_OFFSETS:
        text = text.replace(word, "")
    for word in WEATHER_NOISE_WORDS:
        text = text.replace(word, "")
    text = re.sub(r"\s+", "", text)
    match = re.search(r"([\u4e00-\u9fff]{2,8})(?:市|县|区)?$", text)
    if not match:
        return None
    city = match.group(1)
    if city in {"今天", "明天", "后天"}:
        return None
    return city


def select_weather_day(
    message: str,
    forecast: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    days = forecast.get("days") or []
    if not days:
        return ("", None)

    label = "近期"
    offset = 0
    for date_word, date_offset in WEATHER_DATE_OFFSETS.items():
        if date_word in message:
            label = date_word
            offset = date_offset
            break

    target_date = (date.today() + timedelta(days=offset)).isoformat()
    for day in days:
        if day.get("date") == target_date:
            return (label, day)

    fallback_index = min(offset, len(days) - 1)
    return (label, days[fallback_index])


def build_weather_tip(day_weather: str, night_weather: str) -> str:
    combined = f"{day_weather}{night_weather}"
    if any(word in combined for word in ("雨", "雷", "阵雨")):
        return "建议带伞或轻便雨衣，并注意路面湿滑。"
    if any(word in combined for word in ("晴", "少云")):
        return "白天注意防晒和补水。"
    return "按温度准备衣物，保留雨具或外套作为备选。"


def _upsert_step(
    steps: list[ChatbotResearchStep],
    next_step: ChatbotResearchStep,
) -> list[ChatbotResearchStep]:
    index = next((idx for idx, step in enumerate(steps) if step.id == next_step.id), -1)
    if index == -1:
        return [*steps, next_step]
    return [next_step if idx == index else step for idx, step in enumerate(steps)]
