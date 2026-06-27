import json


INTENT_CLASSIFIER_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent",
        "reason",
        "answer_strategy",
        "search_query",
        "search_queries",
        "generation_tasks",
        "research_topics",
        "edit_scope",
        "missing_slots",
    ],
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "ask",
                "update",
                "search",
                "research",
                "clarify",
                "risk_check",
                "compare",
                "personalize",
            ],
        },
        "reason": {"type": "string"},
        "answer_strategy": {"type": ["string", "null"]},
        "search_query": {"type": ["string", "null"]},
        "search_queries": {"type": "array", "items": {"type": "string"}},
        "generation_tasks": {"type": "array", "items": {"type": "string"}},
        "research_topics": {"type": "array", "items": {"type": "string"}},
        "edit_scope": {
            "type": ["string", "null"],
            "description": "如能判断第几天，格式为 day_1/day_2；否则为 null。",
        },
        "missing_slots": {"type": "array", "items": {"type": "string"}},
    },
}


def _build_intent_classifier_system_prompt(
    output_schema_: dict[str, object] = INTENT_CLASSIFIER_OUTPUT_SCHEMA,
) -> str:
    return (
        "你是智旅顾问的意图分类器、意图分析与执行计划器。"
        "所有请求都必须先分析意图，再制定查询、生成、回答计划；禁止使用关键词匹配做路由。\n\n"
        "intent 含义："
        "ask=询问当前行程、产品用法或可直接回答的旅行问题；"
        "update=修改当前结果页 itinerary；大范围、含糊或会影响多天的修改，优先 clarify 或给出明确 edit_scope。"
        "search=单点联网查询新的事实、开放时间、天气、门票、交通或近期信息；"
        "research=综合旅行推荐或多步骤联网调研，例如热门景点、美食、住宿、预算、交通、天气、景区公告、政策、安全和装备建议；"
        "risk_check=检查行程风险，例如天气、闭馆、交通过远、行程过赶或预算异常；"
        "compare=比较两个或多个旅行方案、住宿区域、交通方式、景点取舍或预算方案；"
        "personalize=根据 traveler_profile 调整推荐、重排行程节奏或解释如何更贴合用户偏好；"
        "clarify=用户目标不清且必须补充信息后才能继续。\n\n"
        "开放式旅游需求如“长沙热门景点推荐”“三天怎么玩”“亲子美食住宿建议”应归为 research，"
        "并给出 search_queries 和 generation_tasks。比较请求要归为 compare；"
        "画像驱动的重排或偏好适配要归为 personalize。"
        "answer_strategy 用一句话说明先查什么、生成什么、最后如何回答。"
        "search_queries 是实际要查的中文查询词数组；generation_tasks 是不需要联网、用于组织答案的生成任务数组。\n\n"
        "只返回一个符合 schema 的 JSON 对象，不要 Markdown，不要解释，不要追加文字。\n\n"
        "<OUTPUT JSON SCHEMA>\n"
        f"{json.dumps(output_schema_, indent=2, ensure_ascii=False)}\n"
        "</OUTPUT JSON SCHEMA>"
    )


INTENT_CLASSIFIER_SYSTEM_PROMPT = _build_intent_classifier_system_prompt()
