# Destination Intelligence Agent

Destination Intelligence Agent 是一个可独立运行的旅行攻略 Agent。它根据目的地、目标日期和同行需求规划研究结构，通过 Tavily 核查最新信息，并经过多轮总结与反思生成可执行的 Markdown 旅行攻略。

当前 Streamlit App 是干净的单 Agent 界面，不包含用户鉴权、权限控制、GitHub 集成、任务 ID、任务恢复或外部任务状态持久化。

## 功能

- 根据自然语言旅行需求生成五部分攻略研究结构
- 使用 Tavily 搜索官方旅行、交通、景点、住宿、餐饮和动态公告
- 对每个攻略部分执行检索、总结和可配置的反思核查
- 在页面中展示完整攻略、来源 URL 与来源发布日期
- 原子保存攻略和可恢复的 JSON 状态到 `destination_intelligence_streamlit_reports/`

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
report = agent.research(
    "2026-10-02至10-06，从东京去京都，2位成人，偏慢节奏，喜欢寺社与美食",
    save_report=True,
)
print(report)
```

默认配置从 `backend/.env` 或当前环境变量读取。

## 目录结构

```text
destination_intelligence_agent/
├── agent.py       # Agent 工作流与公开入口
├── llms/          # LLM 客户端
├── nodes/         # 攻略结构、搜索、总结、反思和格式化节点
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

1. 生成旅行约束、交通住宿、景点餐饮、逐日行程、行前准备五部分研究结构。
2. 为每部分选择通用、深度、近期或发布日期范围搜索策略。
3. 基于带 URL 和发布日期的搜索结果生成首次总结。
4. 按配置执行反思检索；无效反思不会覆盖已有正确内容。
5. 整合全部部分，生成攻略并原子保存 Markdown 与 JSON 状态。
