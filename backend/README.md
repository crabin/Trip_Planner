# Backend 开发说明

当前 `backend/` 是 TripPlannerDemo 的后端项目，提供 FastAPI 接口、行程生成编排、深度规划任务、RAG 检索、地图与天气补充、历史存储、导出服务和浮动聊天助手接口。

## 1. 当前能力

- 快速规划：`POST /trip/generate` 生成结构化 itinerary
- 深度规划：`POST /trip/deep-generate` 创建后台研究任务，生成带来源的 Markdown 攻略
- Report 转行程：把深度规划报告或历史 Markdown Report 转换为结果页 itinerary
- 聊天助手：`POST /chatbot/message` 支持问答、联网搜索和当前行程修改
- 地图与天气：接入高德 Web 服务，为景点、路线、天气和本地生活推荐补充数据
- 历史与导出：支持保存、查询、删除历史行程，并导出 Markdown / PDF

## 2. 项目展示

完整界面展示素材统一放在 [`../assets/showcase/`](../assets/showcase/README.md)。后端主要支撑其中的快速规划、深度规划、报告转换、聊天助手、历史与导出链路。

| 行程生成结果 | 深度规划研究过程 |
| :---: | :---: |
| <img src="../assets/showcase/02行程生成界面.png" alt="行程生成界面" width="420"> | <img src="../assets/showcase/03%20深度规划研究过程.png" alt="深度规划研究过程" width="420"> |

- 浮动聊天助手演示：[`聊天机器人运行.mp4`](../assets/showcase/聊天机器人运行.mp4)
- 深度规划报告样例：[`厦门、汕头 15天14晚旅行攻略`](../assets/showcase/深度规划结果-厦门、汕头%202026-07-01%20至%202026-07-15（15天14晚）旅行攻略.md)

## 3. 启动方式

```bash
cd backend
uv sync
cp .env.example .env
uv run python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

启动后访问：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
```

## 4. 测试

```bash
cd backend
uv run pytest -q
```
