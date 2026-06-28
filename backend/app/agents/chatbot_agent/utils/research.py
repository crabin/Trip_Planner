from __future__ import annotations

import re

from app.models.schemas import ChatbotMessageRequest, ChatbotResearchStep

from ..state import IntentDecision

MAX_RESEARCH_QUERIES = 6


def build_research_queries(text: str, destination: str) -> list[str]:
    origin, inferred_destination = infer_origin_destination(text)
    place = destination or inferred_destination or infer_destination_from_text(text) or "目的地"
    queries: list[str] = []

    if origin and place and origin != place:
        queries.append(f"{origin}到{place} 高铁 火车 自驾 时长 班次")
    elif any(term in text for term in ("交通", "出发", "抵达", "怎么去", "到")):
        queries.append(f"{text} 交通方式 时长 接驳")

    if any(term in text for term in ("两天", "2天", "二天", "两日", "2日", "二日")):
        queries.append(f"{place} 两天 热门景点 路线 行程")
    elif any(term in text for term in ("三天", "3天", "三日", "3日")):
        queries.append(f"{place} 三天 热门景点 路线 行程")
    elif any(term in text for term in ("景点", "热门", "推荐", "必去", "打卡", "怎么玩", "行程", "路线")):
        queries.append(f"{place} 热门景点 推荐 路线")

    if any(term in text for term in ("景点", "热门", "推荐", "必去", "博物馆", "景区", "门票", "预约", "开放")):
        queries.append(f"{place} 热门景点 开放时间 门票 预约")

    if any(term in text for term in ("住宿", "酒店", "住哪", "两天", "2天", "二天", "两日", "2日", "二日")):
        queries.append(f"{place} 住宿区域 景点交通 便利")

    if any(term in text for term in ("返程", "往返", "两天", "2天", "二天", "两日", "2日", "二日")) and origin and place:
        queries.append(f"{place}到{origin} 高铁 返程 班次")

    if not queries:
        queries.append(text)
    return normalize_research_queries(queries)


def build_research_steps(
    request: ChatbotMessageRequest,
    decision: IntentDecision,
) -> list[ChatbotResearchStep]:
    queries = normalize_research_queries(decision.search_queries)
    if not queries:
        queries = build_default_research_queries(request, decision)
    steps = [
        ChatbotResearchStep(
            id="understand",
            title="已理解需求",
            status="completed",
            summary=build_understanding_summary(request, decision),
        ),
        *(
            ChatbotResearchStep(
                id=f"search_{index}",
                title=build_query_step_title(query),
                status="pending",
                query=query,
            )
            for index, query in enumerate(queries[:MAX_RESEARCH_QUERIES], start=1)
        )
    ]
    return steps


def normalize_research_queries(queries: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for query in queries:
        clean = " ".join(str(query).split())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
    return normalized[:MAX_RESEARCH_QUERIES]


def build_query_step_title(query: str) -> str:
    if any(term in query for term in ("天气", "气温", "降雨", "下雨", "穿衣")):
        return "查询天气和穿衣建议"
    if any(term in query for term in ("高铁", "火车", "自驾", "航班", "交通", "接驳", "班次")):
        return "查询交通方式和接驳信息"
    if any(term in query for term in ("景区", "景点", "开放", "门票", "预约", "闭馆", "公告", "营业时间")):
        return "查询景区开放和预约信息"
    if any(term in query for term in ("住宿", "酒店", "住哪", "商圈")):
        return "查询住宿区域和交通便利度"
    if any(term in query for term in ("美食", "餐厅", "小吃", "夜市")):
        return "查询餐饮和夜间体验"
    if any(term in query for term in ("路线", "行程", "两天", "三天", "热门景点", "必去", "推荐")):
        return "查询热门景点和路线建议"
    if any(term in query for term in ("安全", "政策", "提醒", "风险")):
        return "查询旅行提醒和风险"
    return "查询相关旅行信息"


def build_default_research_queries(
    request: ChatbotMessageRequest,
    decision: IntentDecision,
) -> list[str]:
    destination = request.current_itinerary.destination if request.current_itinerary is not None else ""
    base = decision.search_query or request.message
    if decision.intent == "compare":
        return normalize_research_queries([
            f"{base} 交通 预算 体验 对比",
            f"{base} 住宿 区域 交通 便利 比较",
            f"{base} 景点 行程 取舍 风险",
        ])
    if decision.intent == "personalize" and request.profile.model_dump(exclude_none=True):
        return normalize_research_queries([
            f"{base} 顺路 少走路 行程 优化",
            f"{destination or base} 适合 {request.profile.pace_preference or '适中'} 节奏 行程",
            f"{destination or base} 餐饮 {','.join(request.profile.food_preferences[:3]) or '本地'} 推荐",
            f"{destination or base} {','.join(request.profile.interests[:3]) or '旅行'} 推荐",
        ])
    return normalize_research_queries(build_research_queries(base, destination))


def infer_origin_destination(text: str) -> tuple[str, str]:
    match = re.search(r"从([\u4e00-\u9fff]{2,10})去([\u4e00-\u9fff]{2,10})", text)
    if not match:
        match = re.search(r"([\u4e00-\u9fff]{2,10})到([\u4e00-\u9fff]{2,10})", text)
    if not match:
        return "", ""
    origin = clean_city_name(match.group(1))
    destination = clean_city_name(match.group(2))
    return origin, destination


def infer_destination_from_text(text: str) -> str:
    match = re.search(r"([\u4e00-\u9fff]{2,10})(?:热门景点|景点|两天|旅游|旅行|怎么玩)", text)
    if not match:
        return ""
    return clean_city_name(match.group(1))


def clean_city_name(value: str) -> str:
    cleaned = re.sub(r"^(从|去|到|在|帮我|查询|查一下|查)", "", value)
    cleaned = re.sub(r"(热门景点|景点|两天|三天|旅游|旅行|出行方案|方案)$", "", cleaned)
    return cleaned.strip(" ，,。！？?的")


def build_planning_steps(
    request: ChatbotMessageRequest,
    decision: IntentDecision,
) -> list[ChatbotResearchStep]:
    steps = [
        ChatbotResearchStep(
            id="understand",
            title="已理解需求",
            status="completed",
            summary=build_understanding_summary(request, decision),
        )
    ]
    if decision.intent in {"update", "personalize"}:
        scope = f"修改范围：{decision.edit_scope}" if decision.edit_scope else "修改范围：由编辑服务结合上下文判断"
        steps.append(
            ChatbotResearchStep(
                id="execute_update",
                title="执行个性化调整" if decision.intent == "personalize" else "执行行程修改",
                status="pending",
                summary=scope,
            )
        )
    elif decision.intent in {"ask", "clarify", "compare"}:
        steps.append(
            ChatbotResearchStep(
                id="answer",
                title="整理比较建议" if decision.intent == "compare" else "整理回答",
                status="pending",
                summary=(
                    "需要先补充：" + "、".join(decision.missing_slots)
                    if decision.missing_slots
                    else (
                        "按体验、交通、预算和风险比较方案。"
                        if decision.intent == "compare"
                        else "根据当前上下文直接回答。"
                    )
                ),
            )
        )
    return steps


def complete_planning_steps(steps: list[ChatbotResearchStep]) -> list[ChatbotResearchStep]:
    return [
        step.model_copy(update={"status": "completed"})
        if step.status == "pending"
        else step
        for step in steps
    ]


def build_understanding_summary(request: ChatbotMessageRequest, decision: IntentDecision) -> str:
    if decision.answer_strategy:
        return decision.answer_strategy
    if request.current_itinerary is not None:
        return f"围绕当前 {request.current_itinerary.destination} 行程，检查实时信息和旅行风险。"
    return f"用户问题：{request.message}"


def guess_destination(text: str) -> str:
    return ""


def summarize_research_without_llm(
    request: ChatbotMessageRequest,
    steps: list[ChatbotResearchStep],
) -> str:
    completed = [step for step in steps if step.status == "completed" and step.query]
    failed = [step for step in steps if step.status == "failed"]
    source_summaries = [
        step.summary
        for step in completed
        if step.summary and "没有找到足够可靠" not in step.summary
    ]
    checked = "、".join(step.query or step.title for step in completed)
    failure_note = (
        "部分信息暂时无法查证，建议出发前再用官方渠道确认。"
        if failed
        else "时效信息建议出发前再次确认。"
    )
    recommendations = build_fallback_recommendations(request.message, source_summaries)
    parts = [
        f"## 我理解你的需求\n你想了解：{request.message}",
        f"## 我查了哪些信息\n{checked or '相关旅行信息'}。",
    ]
    parts.extend(
        [
            "## 建议",
            recommendations,
            "## 需要再次确认",
            f"{failure_note} 景区开放时间、门票和预约规则请以官方当天信息为准。",
        ]
    )
    return "\n\n".join(parts)


def build_fallback_recommendations(question: str, source_summaries: list[str]) -> str:
    if not source_summaries:
        return "- 暂时没有足够可靠的搜索摘要，建议换一个更具体的景点、日期或偏好再查。"
    return (
        "- 已完成搜索，但当前 LLM 总结不可用，系统不会用关键词规则拼装结论，"
        "避免给出错误或跨城市的推荐。请稍后重试，或检查 LLM API 配置后重新生成回答。"
    )
