from __future__ import annotations

from app.agents.destination_intelligence_agent.agent import DestinationIntelligenceAgent
from app.agents.destination_intelligence_agent.nodes.formatting_node import (
    ReportFormattingNode,
)
from app.agents.destination_intelligence_agent.nodes.report_structure_node import (
    ReportStructureNode,
)
from app.agents.destination_intelligence_agent.prompts import (
    SYSTEM_PROMPT_FIRST_SEARCH,
    SYSTEM_PROMPT_FIRST_SUMMARY,
    SYSTEM_PROMPT_REFLECTION,
    SYSTEM_PROMPT_REPORT_FORMATTING,
    SYSTEM_PROMPT_REPORT_STRUCTURE,
)
from app.agents.destination_intelligence_agent.state import State
from app.agents.destination_intelligence_agent.utils.text_processing import (
    format_search_results_for_prompt,
)


class FakeLLM:
    def __init__(self, response: str = "# 京都旅行攻略\n\n可执行行程") -> None:
        self.response = response
        self.system_prompt = ""
        self.user_prompt = ""

    def stream_invoke_to_string(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.response


def test_prompts_define_a_complete_time_aware_travel_guide() -> None:
    assert "游览或度假" in SYSTEM_PROMPT_REPORT_STRUCTURE
    assert "目标时段" in SYSTEM_PROMPT_REPORT_STRUCTURE
    assert "未来旅行日期误当成发布日期" in SYSTEM_PROMPT_FIRST_SEARCH
    assert "已核实事实" in SYSTEM_PROMPT_FIRST_SUMMARY
    assert "交通与开放时间是否可衔接" in SYSTEM_PROMPT_REFLECTION

    required_final_sections = [
        "行前先做",
        "每日行程",
        "交通与住宿方案",
        "景点、餐饮与备选池",
        "行李检查清单",
        "预算",
        "实用提示与风险预案",
        "出发前一致性检查",
        "资料来源与更新说明",
    ]
    assert all(section in SYSTEM_PROMPT_REPORT_FORMATTING for section in required_final_sections)
    assert "新闻分析报告" not in SYSTEM_PROMPT_REPORT_FORMATTING
    assert "不得包含追问" in SYSTEM_PROMPT_REPORT_FORMATTING
    assert "下一步" in SYSTEM_PROMPT_REPORT_FORMATTING


def test_default_outline_covers_the_five_guide_workstreams() -> None:
    node = ReportStructureNode(FakeLLM(), "2026年10月京都5日游")

    structure = node._generate_default_structure()

    assert len(structure) == 5
    titles = " ".join(item["title"] for item in structure)
    assert "目标时段约束" in titles
    assert "交通" in titles and "住宿" in titles
    assert "景点" in titles and "餐饮" in titles
    assert "逐日" in titles
    assert "风险预案" in titles


def test_incomplete_llm_outline_falls_back_to_all_five_workstreams() -> None:
    node = ReportStructureNode(FakeLLM(), "2026年10月京都5日游")

    structure = node.process_output(
        '[{"title":"只有概览","content":"缺少其余规划部分"}]'
    )

    assert len(structure) == 5
    assert structure[3]["title"] == "逐日可执行行程"


def test_search_results_keep_source_metadata_for_citations() -> None:
    formatted = format_search_results_for_prompt(
        [
            {
                "title": "京都市官方观光指南",
                "url": "https://kyoto.example/official",
                "published_date": "2026-06-01",
                "score": 0.98,
                "content": "秋季寺院预约信息",
            }
        ]
    )

    assert formatted == [
        "标题: 京都市官方观光指南\n"
        "URL: https://kyoto.example/official\n"
        "发布日期: 2026-06-01\n"
        "相关度: 0.98\n"
        "内容: 秋季寺院预约信息"
    ]


def test_search_state_preserves_source_publication_date() -> None:
    state = State(query="京都旅行")
    paragraph_index = state.add_paragraph("时段情报", "核查目标日期")

    state.paragraphs[paragraph_index].research.add_search_results(
        "京都 2026年10月 官方公告",
        [
            {
                "title": "官方公告",
                "url": "https://kyoto.example/notice",
                "content": "预约调整",
                "published_date": "2026-06-01",
            }
        ],
    )

    restored = State.from_dict(state.to_dict())
    assert restored.paragraphs[0].research.search_history[0].published_date == "2026-06-01"


def test_report_formatter_accepts_context_contract_and_legacy_sections() -> None:
    complete_guide = """# 京都旅行攻略

## 行前先做
确认车票、住宿与预约。

## 每日行程
D1 抵达京都。

## 交通与住宿方案
使用公共交通，住宿选择京都站附近。

## 景点、餐饮与备选池
主选清水寺，雨天备选京都国立博物馆。

## 行李检查清单
- [ ] 证件与充电器

## 预算
按交通、住宿、餐饮和门票分类预留。

## 实用提示与风险预案
高温时减少正午步行。

## 出发前一致性检查
- [ ] 日期与晚数一致

## 资料来源与更新说明
出发前复核官方信息。
"""
    llm = FakeLLM(complete_guide)
    node = ReportFormattingNode(llm)
    sections = [{"title": "逐日行程", "paragraph_latest_state": "D1 抵达"}]
    guide_input = {
        "trip_context": "2026-10-02至10-06京都旅行",
        "report_title": "京都旅行攻略",
        "sections": sections,
    }

    assert node.validate_input(guide_input)
    assert node.validate_input(sections)
    assert node.run(guide_input).startswith("# 京都旅行攻略")
    assert "2026-10-02至10-06京都旅行" in llm.user_prompt


def test_manual_report_fallback_uses_travel_language() -> None:
    node = ReportFormattingNode(FakeLLM())

    report = node.format_report_manually(
        [{"title": "每日行程", "paragraph_latest_state": "D1 抵达并入住"}],
        "京都旅行攻略",
    )

    assert report.startswith("# 京都旅行攻略")
    assert "出发前复核" not in report  # 单部分报告不追加重复提醒
    assert "深度搜索和研究" not in report


def test_new_research_resets_state_from_a_previous_trip() -> None:
    agent = object.__new__(DestinationIntelligenceAgent)
    agent.state = State(query="旧旅行")
    agent.state.add_paragraph("旧段落", "不应保留")

    def generate_structure(query: str) -> None:
        agent.state.add_paragraph("新行程", query)

    agent._generate_report_structure = generate_structure
    agent._process_paragraphs = lambda: None
    agent._generate_final_report = lambda: "# 新攻略"
    agent._save_report = lambda report: None

    report = agent.research("2026年京都旅行", save_report=False)

    assert report == "# 新攻略"
    assert agent.state.query == "2026年京都旅行"
    assert [paragraph.title for paragraph in agent.state.paragraphs] == ["新行程"]


def test_final_formatting_receives_original_trip_context() -> None:
    agent = object.__new__(DestinationIntelligenceAgent)
    agent.state = State(query="2026-10-02至10-06京都亲子游", report_title="京都旅行攻略")
    paragraph_index = agent.state.add_paragraph("逐日行程", "研究每日安排")
    agent.state.paragraphs[paragraph_index].research.latest_summary = "D1 抵达京都"

    class CapturingFormatter:
        def __init__(self) -> None:
            self.input_data = None

        def run(self, input_data):
            self.input_data = input_data
            return "# 京都旅行攻略"

    formatter = CapturingFormatter()
    agent.report_formatting_node = formatter

    report = agent._generate_final_report()

    assert report == "# 京都旅行攻略"
    assert formatter.input_data["trip_context"] == "2026-10-02至10-06京都亲子游"
    assert formatter.input_data["sections"][0]["title"] == "逐日行程"
    assert agent.state.is_completed
