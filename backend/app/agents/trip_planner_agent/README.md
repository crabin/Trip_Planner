# Trip Planner Agent

The package is split by responsibility so model providers, prompts, parsing,
and domain state can evolve independently:

```text
trip_planner_agent/
├── agent.py       # public workflow orchestration and fallback boundary
├── llms/          # model settings and client factories
├── nodes/         # context collection and structured generation steps
├── tools/         # RAG query and deterministic arithmetic tools
├── utils/         # provider-response and JSON parsing helpers
├── state/         # Pydantic models exchanged by workflow steps
└── prompts/       # planning and single-day editing prompt builders
```

Import workflow functions from `app.agents.trip_planner_agent`. Focused code
may import its owning submodule directly. The former `app.agents.tools` paths
remain as compatibility aliases for scripts and downstream callers.

## 项目展示

该 Agent 在主项目中支撑快速规划和单日编辑。完整展示素材位于 [`../../../../assets/showcase/`](../../../../assets/showcase/README.md)，其中快速规划相关内容包括：

| 规划页 | 行程生成结果 |
| :---: | :---: |
| <img src="../../../../assets/showcase/01规划界面.png" alt="规划界面" width="420"> | <img src="../../../../assets/showcase/02行程生成界面.png" alt="行程生成界面" width="420"> |

浮动聊天助手演示：[`聊天机器人运行.mp4`](../../../../assets/showcase/聊天机器人运行.mp4)
