# Destination Intelligence Agent

Destination Intelligence Agent 是一个可独立运行的目的地情报研究 Agent。它使用 LLM 规划报告结构，通过 Tavily 搜索最新信息，并经过多轮总结与反思生成 Markdown 研究报告。

当前 Streamlit App 是干净的单 Agent 界面，不包含用户鉴权、权限控制、GitHub 集成、任务 ID、任务恢复或外部任务状态持久化。

## 功能

- 根据自然语言主题生成结构化研究报告
- 使用 Tavily 搜索新闻和网页信息
- 对每个报告段落执行检索、总结和可配置的反思优化
- 在页面中展示最终报告与引用信息
- 将报告保存到本地 `destination_intelligence_streamlit_reports/` 目录

## 配置

在 `backend/.env` 中配置以下环境变量：

```dotenv
DESTINATION_INTELLIGENCE_AGENT_API_KEY=your-llm-api-key
DESTINATION_INTELLIGENCE_AGENT_BASE_URL=your-llm-base-url
DESTINATION_INTELLIGENCE_AGENT_MODEL_NAME=your-model-name
TAVILY_API_KEY=your-tavily-api-key
```

`DESTINATION_INTELLIGENCE_AGENT_BASE_URL` 可选，其余三项为必填项。也可以直接通过当前 shell 的环境变量提供这些配置。

## 启动 Streamlit App

从项目根目录进入后端并安装依赖：

```bash
cd backend
uv sync
```

启动服务：

```bash
uv run streamlit run app/agents/SingleAgentApp/destination_intelligence_agent_streamlit_app.py \
  --server.port 8501 \
  --browser.gatherUsageStats false
```

浏览器访问：

```text
http://localhost:8501
```

按 `Ctrl+C` 关闭服务。如果 8501 端口已被占用，可将 `--server.port` 改为其他端口。

## 代码调用

在 `backend` 目录下可以直接调用 Agent：

```python
from app.agents.destination_intelligence_agent import DestinationIntelligenceAgent

agent = DestinationIntelligenceAgent()
report = agent.research("对比京都与大阪的亲子旅行体验", save_report=True)
print(report)
```

默认配置从 `backend/.env` 或当前环境变量读取。

## 目录结构

```text
destination_intelligence_agent/
├── agent.py       # Agent 工作流与公开入口
├── llms/          # LLM 客户端
├── nodes/         # 报告结构、搜索、总结、反思和格式化节点
├── tools/         # Tavily 搜索工具
├── utils/         # 配置、重试和文本处理
├── state/         # 工作流状态模型
└── prompts/       # 各节点使用的提示词
```

Streamlit 入口位于：

```text
backend/app/agents/SingleAgentApp/destination_intelligence_agent_streamlit_app.py
```

## 工作流程

1. 根据研究主题生成报告结构。
2. 为每个段落选择搜索策略并获取资料。
3. 基于搜索结果生成首次总结。
4. 按配置执行反思检索和总结优化。
5. 整合全部段落，生成并保存最终报告。
