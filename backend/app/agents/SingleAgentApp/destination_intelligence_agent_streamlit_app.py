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

from app.agents.destination_intelligence_agent import (  # noqa: E402
    DestinationIntelligenceAgent,
    Settings,
)


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
    st.header("旅行攻略")
    report_tab, sources_tab = st.tabs(["完整攻略", "研究来源"])

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
                    if search.published_date:
                        st.caption(f"来源发布日期：{search.published_date}")

        if source_count == 0:
            st.info("本次研究没有返回可展示的引用信息。")


def main() -> None:
    st.set_page_config(
        page_title="Destination Intelligence Agent",
        page_icon="🌏",
        layout="wide",
    )

    st.title("Destination Intelligence Agent")
    st.caption("根据目的地、目标日期和同行需求生成可执行旅行攻略")

    with st.sidebar:
        st.subheader("攻略研究设置")
        max_paragraphs = 5
        st.caption("攻略研究固定为 5 个相互依赖的部分。")
        max_reflections = st.slider("每部分补充核查轮数", 0, 4, 2)
        st.caption("API 密钥从 backend/.env 或当前环境变量读取。")

    with st.form("research_form"):
        query = st.text_area(
            "旅行需求",
            placeholder="例如：2026-10-02 至 10-06，从东京出发去京都，2位成人，偏慢节奏，预算约20万日元，喜欢寺社与美食",
            height=120,
        )
        submitted = st.form_submit_button("生成旅行攻略", type="primary")

    if submitted:
        if not query.strip():
            st.warning("请先输入目的地、目标日期和旅行需求。")
        else:
            try:
                config = create_config(max_reflections, max_paragraphs)
                with st.spinner("Agent 正在核查时段信息并生成旅行攻略……"):
                    st.session_state.research_result = run_research(query.strip(), config)
            except ValidationError as exc:
                missing_fields = ", ".join(
                    str(error["loc"][0]) for error in exc.errors() if error["type"] == "missing"
                )
                st.error(f"缺少必要环境变量：{missing_fields or '请检查 backend/.env'}")
            except Exception as exc:
                logger.exception("Destination Intelligence Agent research failed")
                st.error(f"攻略生成失败：{exc}")

    result = st.session_state.get("research_result")
    if result:
        display_results(*result)


if __name__ == "__main__":
    main()
