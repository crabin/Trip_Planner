from __future__ import annotations

import json

from app.agents.report_itinerary_agent.state import (
    ChunkExtraction,
    ReportExtractionSection,
)


SYSTEM_PROMPT = (
    "你是旅行 Report 的忠实结构化抽取器。只使用输入中明确出现的信息，"
    "不补写、不猜测、不把住宿晚数或候选清单当作逐日行程。"
    "所有未知时间、费用、地点和交通字段必须留空。"
)


def build_chunk_batch_prompt(
    *,
    sections: list[ReportExtractionSection],
    destination: str,
    title: str,
) -> str:
    chunks = [
        {
            "chunk_id": section.section_id,
            "heading_path": list(section.heading_path),
            "markdown": section.markdown,
        }
        for section in sections
    ]
    return f"""
请逐个抽取下面的 Report 小结。每个 chunk_id 必须且只能返回一次，即使该块与结果页无关，也要返回 section_kind=other 和空 extracted。

规则：
1. section_kind 由内容语义判断，不能根据固定标题关键词硬套。
2. 只有描述某个完整旅行日或该日组成部分的内容才能写入 days；逐晚住宿表、候选池、预算表不能生成 days。
3. 同一天被拆成多个小结时，可以分别返回同一个 day_index/date，并在 source_chunk_ids 中写当前 chunk_id；最终汇总器会合并。
4. spots 仅包含当天确定执行、可地图检索的真实地点；备选信息保留在 full_day_text，不强行生成地图点。
5. start_time/end_time/cost 只有原文明确给出时才填写。免费填 0，未知填 null。
6. overview_facts 使用稳定英文 key，优先采用 date_range、travelers、origin、pace、preferences、intercity_transport、local_transport、lodging、budget_scope、assumptions、confirmations。
7. map_query 应包含目的地和地点/区域，但不得创造原文没有的具体商户。
8. 保留原文中的完整日程说明，不要把它压缩成一句占位文案。

目的地：{destination}
Report 标题：{title}
小结 JSON：
{json.dumps(chunks, ensure_ascii=False)}
""".strip()


def build_consolidation_prompt(
    *,
    extractions: list[ChunkExtraction],
    destination: str,
    title: str,
    start_date: str | None,
    end_date: str | None,
) -> str:
    payload = []
    for item in extractions:
        extracted = item.extracted.model_dump(
            mode="json",
            exclude_none=True,
            exclude_defaults=True,
        )
        if not extracted:
            continue
        payload.append(
            {
                "chunk_id": item.chunk_id,
                "section_kind": item.section_kind,
                "extracted": extracted,
            }
        )
    return f"""
请把所有 Report 小结抽取结果汇总成一个唯一、完整的 ExtractedReport。

规则：
1. 语义合并同一天的部分信息，去重重复提示、景点、餐饮与住宿；不得丢失返程日。
2. 住宿表只能补充对应日的 hotel 字段，不能独立创造日程。
3. 候选池只能补充说明，不能覆盖每日行程中已经明确的主点。
4. day_index 必须从 1 连续递增；有明确日期时按日期顺序排列。
5. start_date、end_date、total_days 必须与最终 days 自洽。调用方提供的日期仅作为一致性提示，不得用它编造缺失日。
6. overview_facts 按 key 语义去重；tips 只保留可执行、非重复的重点提示。
7. 未知费用保持 null；total_budget 只使用 Report 明确给出的总预算。
8. 每个 day.source_chunk_ids 保留所有贡献该日信息的 chunk_id。
9. 输入中省略了无结果的 chunk 和部分冗余字段；不要因此认为原 Report 缺少这些 chunk。

目的地：{destination}
Report 标题：{title}
调用方日期提示：{start_date or "未知"} 至 {end_date or "未知"}
小结抽取结果：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_section_extraction_user_prompt(
    *,
    section: ReportExtractionSection,
    destination: str,
    title: str,
) -> str:
    """Compatibility wrapper for single-section callers."""

    return build_chunk_batch_prompt(
        sections=[section],
        destination=destination,
        title=title,
    )
