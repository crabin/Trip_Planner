import os
from pathlib import Path

from dotenv import load_dotenv

from app.core.database import (
    BACKEND_DIR,
    DATABASE_URL,
    DB_DIR,
    SQLITE_DB_PATH,
    Base,
    SessionLocal,
    engine,
)


load_dotenv(BACKEND_DIR / ".env")


def _env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


# 大模型配置
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_TIMEOUT_SECONDS = _env_int("LLM_TIMEOUT_SECONDS", 60, minimum=1, maximum=600)
LLM_MAX_RETRIES = _env_int("LLM_MAX_RETRIES", 1, minimum=0, maximum=10)
REPORT_ITINERARY_LLM_TIMEOUT_SECONDS = _env_int(
    "REPORT_ITINERARY_LLM_TIMEOUT_SECONDS",
    180,
    minimum=1,
    maximum=900,
)
REPORT_ITINERARY_MAX_CONCURRENT_BATCHES = _env_int(
    "REPORT_ITINERARY_MAX_CONCURRENT_BATCHES",
    2,
    minimum=1,
    maximum=8,
)


# RAG / 向量库配置
_chroma_db_dir_raw = Path(os.getenv("CHROMA_DB_DIR", "db/chroma_db"))
CHROMA_DB_DIR = (
    _chroma_db_dir_raw
    if _chroma_db_dir_raw.is_absolute()
    else BACKEND_DIR / _chroma_db_dir_raw
)
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "travel_guides")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")
EMBEDDING_BATCH_SIZE = _env_int("EMBEDDING_BATCH_SIZE", 10, minimum=1, maximum=128)


# Redis / 缓存配置
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "trip_planner")
REDIS_DEFAULT_TTL_SECONDS = _env_int("REDIS_DEFAULT_TTL_SECONDS", 1800, minimum=1)
REDIS_WEATHER_TTL_SECONDS = _env_int("REDIS_WEATHER_TTL_SECONDS", 1800, minimum=1)
REDIS_MAP_TTL_SECONDS = _env_int("REDIS_MAP_TTL_SECONDS", 86400, minimum=1)
REDIS_RAG_TTL_SECONDS = _env_int("REDIS_RAG_TTL_SECONDS", 21600, minimum=1)


# 高德地图配置
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_BASE_URL = os.getenv("AMAP_BASE_URL", "https://restapi.amap.com/v3")
AMAP_DEFAULT_CITY = os.getenv("AMAP_DEFAULT_CITY", "")
AMAP_TIMEOUT_SECONDS = _env_int("AMAP_TIMEOUT_SECONDS", 20, minimum=1, maximum=120)
ENABLE_AMAP_ENRICHMENT = os.getenv("ENABLE_AMAP_ENRICHMENT", "false").lower() == "true"


# 12306 MCP / 实时铁路余票配置
ENABLE_12306_MCP = os.getenv("ENABLE_12306_MCP", "false").lower() == "true"
MCP_12306_URL = os.getenv("MCP_12306_URL", "")
MCP_12306_TIMEOUT_SECONDS = _env_int("MCP_12306_TIMEOUT_SECONDS", 30, minimum=1, maximum=120)
MCP_12306_MAX_RESULTS = _env_int("MCP_12306_MAX_RESULTS", 20, minimum=1, maximum=100)


# 美团 / 大众点评等本地生活配置
ENABLE_LOCAL_LIFE_ENRICHMENT = (
    os.getenv("ENABLE_LOCAL_LIFE_ENRICHMENT", "false").lower() == "true"
)
LOCAL_LIFE_TIMEOUT_SECONDS = _env_int("LOCAL_LIFE_TIMEOUT_SECONDS", 20, minimum=1, maximum=120)
MEITUAN_API_BASE_URL = os.getenv("MEITUAN_API_BASE_URL", "")
MEITUAN_API_KEY = os.getenv("MEITUAN_API_KEY", "")
DIANPING_API_BASE_URL = os.getenv("DIANPING_API_BASE_URL", "")
DIANPING_API_KEY = os.getenv("DIANPING_API_KEY", "")
