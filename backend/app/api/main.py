from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.chatbot import router as chatbot_router
from app.api.routes.export import router as export_router
from app.api.routes.location import router as location_router
from app.api.routes.trip import router as trip_router
from app.api.routes.weather import router as weather_router


app = FastAPI(
    title="Trip Planner Demo Backend",
    description="MVP backend for the intelligent travel assistant.",
    version="0.1.0",
)

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """健康检查接口。"""
    return {"status": "ok"}


app.include_router(trip_router)
app.include_router(chatbot_router)
app.include_router(export_router)
app.include_router(weather_router)
app.include_router(location_router)


if FRONTEND_DIST.is_dir():
    # API 路由必须先注册；根挂载最后兜底提供由 Vite 构建的 Web 首页与静态资源。
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/")
    def read_root() -> dict[str, str]:
        """开发环境未构建前端时，用于确认后端服务已启动。"""
        return {"message": "Trip Planner Demo backend is running."}
