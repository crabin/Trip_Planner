from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.destination_intelligence_agent.agent import DestinationIntelligenceAgent
from app.agents.tools.transport_tool import TransportToolResult
from app.agents.destination_intelligence_agent.nodes.search_node import (
    FirstSearchNode,
    ReflectionNode,
)
from app.agents.destination_intelligence_agent.nodes.formatting_node import (
    ReportFormattingNode,
)
from app.agents.destination_intelligence_agent.nodes.summary_node import (
    FirstSummaryNode,
    ReflectionSummaryNode,
)
from app.agents.destination_intelligence_agent.state import State
from app.agents.destination_intelligence_agent.utils.text_processing import (
    extract_clean_response,
)
from app.services.transport_query_service import TrainTicket


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    def stream_invoke_to_string(self, system_prompt: str, user_prompt: str) -> str:
        return self.response


class SequencedFakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = 0

    def stream_invoke_to_string(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        return next(self.responses)


def build_complete_guide(*, conversational_tail: bool = False) -> str:
    guide = """# 厦门 2026-07-02至07-06（5天4晚）旅行攻略

> 两位成人从长沙出发，偏慢节奏。

## 行前先做（按截止时间）
- 预订交通与住宿。

## 每日行程
### D1（7月2日）抵达厦门
- 14:00 入住并休息。

## 交通与住宿方案
- 优先中山路片区。

## 景点、餐饮与备选池
- 鼓浪屿作为主选，植物园作为雨天备选。

## 行李检查清单
- [ ] 身份证
- [ ] 防晒用品

## 预算
- 2人总预算约10000元，待交通价格确认。

## 实用提示与风险预案
- 台风或暴雨时改为室内路线。

## 出发前一致性检查
- [ ] 日期与晚数一致
- [ ] 逐晚住宿覆盖4晚

## 资料来源与更新说明
- 厦门官方旅游信息，2026-06核验。
"""
    if conversational_tail:
        guide += "\n如果你愿意，我下一步可以继续补充酒店和餐厅候选。\n"
    return guide


def test_first_search_preserves_selected_tool() -> None:
    node = FirstSearchNode(FakeLLM(""))

    result = node.process_output(
        '{"search_query":"厦门景点官方预约","search_tool":"deep_search_news",'
        '"reasoning":"需要比较多个官方来源"}'
    )

    assert result["search_tool"] == "deep_search_news"


def test_reflection_preserves_date_search_parameters() -> None:
    node = ReflectionNode(FakeLLM(""))

    result = node.process_output(
        '{"search_query":"厦门近期关闭公告",'
        '"search_tool":"search_news_by_date",'
        '"reasoning":"核查目标日期前发布的公告",'
        '"start_date":"2026-06-01","end_date":"2026-06-22"}'
    )

    assert result["search_tool"] == "search_news_by_date"
    assert result["start_date"] == "2026-06-01"
    assert result["end_date"] == "2026-06-22"


def test_search_nodes_preserve_train_ticket_query_tool() -> None:
    node = FirstSearchNode(FakeLLM(""))

    result = node.process_output(
        '{"search_query":"上海到杭州 2026-06-28 上午 高铁 直达",'
        '"search_tool":"train_ticket_query",'
        '"reasoning":"跨市铁路段需要查12306实时余票"}'
    )

    assert result["search_tool"] == "train_ticket_query"


def test_destination_agent_executes_train_ticket_query_as_search_evidence(monkeypatch) -> None:
    agent = object.__new__(DestinationIntelligenceAgent)
    agent.search_agency = None

    captured = {}

    def fake_transport_tool(message: str, search_query: str = "") -> TransportToolResult:
        captured["message"] = message
        captured["search_query"] = search_query
        return TransportToolResult(
            available=True,
            answer="## 推荐直达车次\n- G205 上海虹桥 07:00 -> 杭州东 07:45",
            source_notes=["来源：中国铁路12306 / 12306 MCP https://www.12306.cn/index/"],
            tickets=[
                TrainTicket(
                    train_code="G205",
                    from_station="上海虹桥",
                    to_station="杭州东",
                    start_time="07:00",
                    arrive_time="07:45",
                    duration="00:45",
                    date="2026-06-28",
                )
            ],
        )

    monkeypatch.setattr(
        "app.agents.destination_intelligence_agent.agent.search_train_tickets_for_agent",
        fake_transport_tool,
    )

    response = agent.execute_search_tool(
        "train_ticket_query",
        "上海到杭州 2026-06-28 上午 高铁 直达",
    )

    assert response.query == "上海到杭州 2026-06-28 上午 高铁 直达"
    assert response.answer == "## 推荐直达车次\n- G205 上海虹桥 07:00 -> 杭州东 07:45"
    assert response.results[0].title == "中国铁路12306 / 12306 MCP"
    assert response.results[0].url == "https://www.12306.cn/index/"
    assert "G205" in response.results[0].content
    assert "12306 官方页面为准" in response.results[0].raw_content
    assert captured == {
        "message": "上海到杭州 2026-06-28 上午 高铁 直达",
        "search_query": "上海到杭州 2026-06-28 上午 高铁 直达",
    }


def test_invalid_search_response_falls_back_to_trip_specific_query() -> None:
    node = FirstSearchNode(FakeLLM("not json"))

    result = node.run(
        {
            "trip_context": "2026年7月长沙到厦门慢节奏旅行",
            "title": "交通与住宿",
            "content": "核查到离交通、接驳和住宿区域",
        }
    )

    assert "厦门" in result["search_query"]
    assert result["search_tool"] == "basic_search_news"


def test_invalid_reflection_summary_keeps_last_good_summary() -> None:
    state = State(query="厦门旅行")
    paragraph_index = state.add_paragraph("逐日行程", "规划每天路线")
    state.paragraphs[paragraph_index].research.latest_summary = "已核实的原始行程"
    node = ReflectionSummaryNode(FakeLLM('{"unexpected":"invalid contract"}'))

    updated = node.mutate_state(
        {
            "title": "逐日行程",
            "content": "规划每天路线",
            "search_query": "补充核查",
            "search_results": [],
            "paragraph_latest_state": "已核实的原始行程",
        },
        state,
        paragraph_index,
    )

    assert updated.paragraphs[paragraph_index].research.latest_summary == "已核实的原始行程"


def test_invalid_first_summary_contract_falls_back_to_search_digest() -> None:
    state = State(query="厦门旅行")
    paragraph_index = state.add_paragraph("交通与住宿", "核查到离交通和住宿区域")
    node = FirstSummaryNode(FakeLLM('{"unexpected":"invalid contract"}'))

    updated = node.mutate_state(
        {
            "trip_context": "2026年7月长沙到厦门慢节奏旅行",
            "title": "交通与住宿",
            "content": "核查到离交通和住宿区域",
            "search_query": "厦门 机场 高铁 住宿 区域",
            "search_results": [
                "标题: 厦门交通攻略\nURL: https://example.com\n内容: 厦门北站可接驳地铁。"
            ],
        },
        state,
        paragraph_index,
    )

    summary = updated.paragraphs[paragraph_index].research.latest_summary
    assert "交通与住宿" in summary
    assert "厦门 机场 高铁 住宿 区域" in summary
    assert "厦门北站可接驳地铁" in summary


def test_first_summary_extracts_valid_json_before_trailing_text() -> None:
    node = FirstSummaryNode(FakeLLM(""))
    response = '{"paragraph_latest_state":"已核实首版攻略"}\n额外说明 }'

    assert node.process_output(response) == "已核实首版攻略"


def test_reflection_summary_extracts_valid_json_before_trailing_text() -> None:
    node = ReflectionSummaryNode(FakeLLM(""))
    response = (
        '{"updated_paragraph_latest_state":"已补充预约与交通信息"}\n'
        "以下是额外说明 }"
    )

    assert node.process_output(response) == "已补充预约与交通信息"


def test_reflection_summary_plain_text_fallback_preserves_checklist() -> None:
    node = ReflectionSummaryNode(FakeLLM(""))
    response = "已核实预约要求\n- [ ] 出发前预约"

    assert node.process_output(response) == response


def test_optional_state_save_failure_does_not_discard_generated_report(
    tmp_path,
    monkeypatch,
) -> None:
    agent = object.__new__(DestinationIntelligenceAgent)
    agent.config = SimpleNamespace(
        OUTPUT_DIR=str(tmp_path),
        SAVE_INTERMEDIATE_STATES=True,
    )
    agent.state = State(query="厦门旅行")

    def fail_state_save(filepath) -> None:
        raise OSError("disk error")

    monkeypatch.setattr(agent.state, "save_to_file", fail_state_save)

    agent._save_report("# 厦门旅行攻略")

    reports = list(tmp_path.glob("travel_guide_*.md"))
    assert len(reports) == 1
    assert reports[0].read_text(encoding="utf-8") == "# 厦门旅行攻略"


def test_incomplete_json_object_repair_preserves_object_contract() -> None:
    parsed = extract_clean_response('{"search_query":"厦门官方交通"')

    assert parsed == {"search_query": "厦门官方交通"}


def test_empty_final_formatter_response_uses_manual_guide_fallback() -> None:
    agent = object.__new__(DestinationIntelligenceAgent)
    agent.state = State(query="厦门旅行", report_title="厦门旅行攻略")
    paragraph_index = agent.state.add_paragraph("逐日行程", "规划每天路线")
    agent.state.paragraphs[paragraph_index].research.latest_summary = "D1 抵达厦门"
    agent.report_formatting_node = ReportFormattingNode(FakeLLM("   "))

    report = agent._generate_final_report()

    assert report.startswith("# 厦门旅行攻略")
    assert "D1 抵达厦门" in report
    assert "生成失败" not in report


def test_final_formatter_preserves_markdown_before_checkboxes() -> None:
    node = ReportFormattingNode(FakeLLM(""))
    guide = build_complete_guide()

    processed = node.process_output(guide)

    assert processed.startswith("# 厦门 2026-07-02至07-06（5天4晚）旅行攻略")
    assert "### D1（7月2日）抵达厦门" in processed
    assert "- [ ] 日期与晚数一致" in processed


def test_final_formatter_removes_conversational_tail() -> None:
    node = ReportFormattingNode(FakeLLM(""))

    processed = node.process_output(build_complete_guide(conversational_tail=True))

    assert "如果你愿意" not in processed
    assert "下一步可以" not in processed
    assert processed.endswith("厦门官方旅游信息，2026-06核验。")


def test_final_formatter_rejects_incomplete_guide() -> None:
    node = ReportFormattingNode(FakeLLM(""))

    with pytest.raises(ValueError, match="缺少必要章节"):
        node.process_output("# 厦门旅行攻略\n\n## 出发前一致性检查\n- [ ] 日期正确")


def test_final_formatter_retries_once_after_contract_failure() -> None:
    llm = SequencedFakeLLM(
        [
            "# 厦门旅行攻略\n\n## 出发前一致性检查\n- [ ] 日期正确",
            build_complete_guide(),
        ]
    )
    node = ReportFormattingNode(llm)

    result = node.run(
        {
            "trip_context": "2026年7月长沙到厦门旅行",
            "report_title": "厦门旅行攻略",
            "sections": [
                {"title": "逐日行程", "paragraph_latest_state": "D1 抵达厦门"}
            ],
        }
    )

    assert llm.calls == 2
    assert result == build_complete_guide().strip()
