"""Standalone Streamlit UI for the Destination Intelligence Agent."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from loguru import logger
from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.destination_intelligence_agent import DestinationIntelligenceAgent, Settings


def create_config(max_reflections: int, max_paragraphs: int) -> Settings:
    """Load secrets from the environment and apply the UI's runtime options."""
    return Settings(
        MAX_REFLECTIONS=max_reflections,
        MAX_PARAGRAPHS=max_paragraphs,
        OUTPUT_DIR="destination_intelligence_streamlit_reports",
    )


def run_research(query: str, config: Settings) -> tuple[DestinationIntelligenceAgent, str]:
    """Run one independent research request."""
    agent = DestinationIntelligenceAgent(config)
    report = agent.research(query, save_report=True)
    return agent, report


def display_results(agent: DestinationIntelligenceAgent, report: str) -> None:
    """Render the report and its search history."""
    st.header("研究结果")
    report_tab, sources_tab = st.tabs(["研究报告", "引用信息"])

    with report_tab:
        st.markdown(report)

    with sources_tab:
        source_count = 0
        for paragraph_index, paragraph in enumerate(agent.state.paragraphs, start=1):
            st.subheader(f"{paragraph_index}. {paragraph.title}")
            for search in paragraph.research.search_history:
                source_count += 1
                label = search.title or search.query or f"来源 {source_count}"
                with st.expander(label):
                    if search.url:
                        st.markdown(f"[打开来源]({search.url})")
                    if search.content:
                        st.write(search.content)
                    if search.score is not None:
                        st.caption(f"相关度：{search.score}")

        if source_count == 0:
            st.info("本次研究没有返回可展示的引用信息。")


def main() -> None:
    st.set_page_config(
        page_title="Destination Intelligence Agent",
        page_icon="🌏",
        layout="wide",
    )

    st.title("Destination Intelligence Agent")
    st.caption("独立运行的目的地情报研究 Agent")

    with st.sidebar:
        st.subheader("研究设置")
        max_paragraphs = st.slider("报告段落数上限", 1, 8, 5)
        max_reflections = st.slider("每段反思轮数", 0, 4, 2)
        st.caption("API 密钥从 backend/.env 或当前环境变量读取。")

    with st.form("research_form"):
        query = st.text_area(
            "研究主题",
            placeholder="例如：对比京都与大阪的亲子旅行体验、预算和最佳季节",
            height=120,
        )
        submitted = st.form_submit_button("开始研究", type="primary")

    if submitted:
        if not query.strip():
            st.warning("请先输入研究主题。")
        else:
            try:
                config = create_config(max_reflections, max_paragraphs)
                with st.spinner("Agent 正在搜索、分析并生成报告……"):
                    st.session_state.research_result = run_research(query.strip(), config)
            except ValidationError as exc:
                missing_fields = ", ".join(
                    str(error["loc"][0]) for error in exc.errors() if error["type"] == "missing"
                )
                st.error(f"缺少必要环境变量：{missing_fields or '请检查 backend/.env'}")
            except Exception as exc:
                logger.exception("Destination Intelligence Agent research failed")
                st.error(f"研究失败：{exc}")

    result = st.session_state.get("research_result")
    if result:
        display_results(*result)


if __name__ == "__main__":
    main()
