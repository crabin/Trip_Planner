import json


REALTIME_QUERY_ROUTER_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query_kind", "search_query", "reason"],
    "properties": {
        "query_kind": {
            "type": "string",
            "enum": [
                "weather",
                "scenic_notice",
                "transport",
                "ticket",
                "business_hours",
                "generic_search",
            ],
        },
        "search_query": {
            "type": "string",
            "description": "适合直接联网搜索；天气查询可只返回城市和日期语义。",
        },
        "reason": {"type": "string", "description": "一句中文说明。"},
    },
}


def _build_realtime_query_router_system_prompt(
    output_schema_: dict[str, object] = REALTIME_QUERY_ROUTER_OUTPUT_SCHEMA,
) -> str:
    return (
        "你是智旅顾问的实时查询路由器。\n\n"
        "query_kind 含义："
        "weather=天气、气温、降雨、穿衣；scenic_notice=景区开放、闭园、施工、预约公告；"
        "transport=航班、高铁、火车、机场车站、交通耗时；ticket=门票、票价、购票、优惠；"
        "business_hours=营业或开放时间；generic_search=其他需要联网的单点事实。\n\n"
        "只返回一个符合 schema 的 JSON 对象，不要 Markdown，不要解释，不要追加文字。\n\n"
        "<OUTPUT JSON SCHEMA>\n"
        f"{json.dumps(output_schema_, indent=2, ensure_ascii=False)}\n"
        "</OUTPUT JSON SCHEMA>"
    )


REALTIME_QUERY_ROUTER_SYSTEM_PROMPT = _build_realtime_query_router_system_prompt()
