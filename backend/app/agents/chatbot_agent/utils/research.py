from __future__ import annotations

from app.models.schemas import ChatbotMessageRequest, ChatbotResearchStep

from ..state import IntentDecision

RESEARCH_STEP_DEFINITIONS = (
    ("weather", "查询天气和穿衣建议", "weather"),
    ("scenic_notice", "查询景区开放、门票和预约公告", "scenic_notice"),
    ("transport", "查询出发和抵达后的交通接驳", "transport"),
    ("policy_safety", "查询当地政策、安全和旅行提醒", "policy_safety"),
    ("packing_health", "整理装备、健康和当地体验注意事项", "packing_health"),
)


def build_research_queries(text: str, destination: str) -> list[str]:
    place = destination or "目的地"
    return [
        f"{place} 下周 天气 预报 穿衣 建议",
        f"{place} 景区 开放公告 门票 预约",
        f"{text} 交通 接驳 注意事项",
        f"{place} 旅游 政策 安全 提醒",
        f"{place} 旅行 防晒 防蚊 雨季 装备 注意事项",
    ]


def build_research_steps(
    request: ChatbotMessageRequest,
    decision: IntentDecision,
) -> list[ChatbotResearchStep]:
    queries = [
        *decision.search_queries,
        *build_default_research_queries(request, decision),
    ]
    steps = [
        ChatbotResearchStep(
            id="understand",
            title="已理解需求",
            status="completed",
            summary=build_understanding_summary(request, decision),
        ),
        *[
            ChatbotResearchStep(
                id=step_id,
                title=title,
                status="pending",
                query=queries[index],
            )
            for index, (step_id, title, _topic) in enumerate(RESEARCH_STEP_DEFINITIONS)
        ],
    ]
    steps.extend(
        ChatbotResearchStep(
            id=f"generate_{index}",
            title="生成回答要点",
            status="completed",
            summary=task,
        )
        for index, task in enumerate(decision.generation_tasks, start=1)
        if task
    )
    return steps


def build_default_research_queries(
    request: ChatbotMessageRequest,
    decision: IntentDecision,
) -> list[str]:
    destination = request.current_itinerary.destination if request.current_itinerary is not None else ""
    base = decision.search_query or request.message
    defaults = build_research_queries(base, destination)
    return defaults[len(decision.search_queries) :]


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
    if decision.intent == "update":
        scope = f"修改范围：{decision.edit_scope}" if decision.edit_scope else "修改范围：由编辑服务结合上下文判断"
        steps.append(
            ChatbotResearchStep(
                id="execute_update",
                title="执行行程修改",
                status="pending",
                summary=scope,
            )
        )
    elif decision.intent in {"ask", "clarify"}:
        steps.append(
            ChatbotResearchStep(
                id="answer",
                title="整理回答",
                status="pending",
                summary=(
                    "需要先补充：" + "、".join(decision.missing_slots)
                    if decision.missing_slots
                    else "根据当前上下文直接回答。"
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
    generation_tasks = [
        step.summary
        for step in steps
        if step.id.startswith("generate_") and step.summary
    ]
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
    plan_note = "；".join(generation_tasks[:3])
    parts = [
        f"## 我理解你的需求\n你想了解：{request.message}",
        f"## 我查了哪些信息\n{checked or '相关旅行信息'}。",
    ]
    if plan_note:
        parts.append(f"## 整理方式\n{plan_note}。")
    parts.extend(
        [
            "## 推荐建议",
            recommendations,
            "## 需要再次确认",
            f"{failure_note} 景区开放时间、门票和预约规则请以官方当天信息为准。",
        ]
    )
    return "\n\n".join(parts)


def build_fallback_recommendations(question: str, source_summaries: list[str]) -> str:
    text = "\n".join(source_summaries)
    if any(term in question for term in ("景点", "推荐", "热门", "必去", "打卡")):
        spots = []
        for name in ("岳麓山", "橘子洲", "湖南博物院", "湖南省植物园", "北辰三角洲", "长沙大悦城"):
            if name in text and name not in spots:
                spots.append(name)
        if not spots:
            spots = ["岳麓山", "橘子洲", "湖南博物院"]
        return "\n".join(
            f"- {name}：可作为长沙热门景点候选，建议结合开放时间、预约要求和当天交通安排选择。"
            for name in spots[:6]
        )
    if source_summaries:
        return "\n".join(f"- {summary}" for summary in source_summaries[:5])
    return "- 暂时没有足够可靠的搜索摘要，建议换一个更具体的景点、日期或偏好再查。"
