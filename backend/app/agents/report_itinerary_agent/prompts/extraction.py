from __future__ import annotations

from app.agents.report_itinerary_agent.state import ReportExtractionSection


SYSTEM_PROMPT = (
    "你是旅行攻略结构化抽取器。只从用户提供的 Markdown Report 中抽取信息，"
    "不要编造价格、餐厅、酒店、景点或交通。输出严格 JSON 对象，不要 Markdown。"
)


def build_section_extraction_user_prompt(
    *,
    section: ReportExtractionSection,
    destination: str,
    title: str,
) -> str:
    return f"""
请把下面这个旅行 Report 的一个章节转换为结果页 itinerary 所需的固定 JSON。

要求：
1. 只抽取当前章节里明确出现的信息。其他章节未知时保持空字符串、空数组或 0。
2. overview 只在当前章节包含“一屏概览/概览/待确认/预算口径”等总览信息时填写，尽量保留原文。
3. total_budget 只填写当前章节明确写出的总预算数字；不要把总预算填到单个景点、餐饮或酒店。
4. days 只填写当前章节明确包含的 D1/D2/每日行程。full_day_text 使用当前章节的完整可读内容。
5. spots 只放真实可地图检索的地点。不要放“2位成人、开放、当前、选择理由、预算、酒店、打车、包车”等非地点。
6. spots 是当天最终用于地图展示的主点，不是候选池。遇到“二选一、若到得早、备选、也可”等候选，只选择一个最适合作为地图主点的地点；其他候选保留在 full_day_text。
7. 每个 spot.name 是前端展示名；spot.map_query 是高德地图检索关键词，必须包含目的地城市并足够精确。例如“北京 王府井”“北京 故宫博物院”。
8. meals/hotel 也请给 map_query。若 Report 只有区域或菜系，就用区域+菜系作为 name/query；不要写“根据深度规划 Report 提取...”等占位文案。
9. 如某价格未知，不要输出 item cost；本 JSON schema 不需要 item cost。

返回 JSON schema：
{{
  "overview": "一屏概览：\\n日期：...",
  "total_budget": 10000,
  "tips": ["..."],
  "days": [
    {{
      "day_index": 1,
      "date": "2026-06-29",
      "theme": "长沙出发，北京入住 + 前门/王府井轻量适应",
      "full_day_text": "时间—地点链\\n...",
      "spots": [
        {{"name": "王府井", "map_query": "北京 王府井", "description": "商圈，适合首日轻量活动"}}
      ],
      "meals": [
        {{"name": "王府井附近京味菜", "meal_type": "晚餐", "map_query": "北京 王府井 京味菜", "notes": "首日晚餐不要排太远"}}
      ],
      "hotel_name": "北京东城核心区酒店",
      "hotel_query": "北京 东城 前门 崇文门 王府井 酒店",
      "transport_note": "地铁为主，打车补位"
    }}
  ]
}}

目的地：{destination}
Report 标题：{title}
章节 ID：{section.section_id}
章节类型：{section.section_type}
章节标题：{section.title}
章节 Markdown：
{section.markdown[:12000]}
"""
