from pathlib import Path
import importlib
import sys
import types


# 允许测试文件直接导入 backend/app 下的模块。
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.services.cache_service as cache_service  # noqa: E402


def test_load_redis_module_uses_current_environment(monkeypatch) -> None:
    """测试当前解释器已安装 redis 时，直接使用当前环境。"""

    fake_redis = types.SimpleNamespace(__name__="redis")

    def fake_import_module(name: str):
        assert name == "redis"
        return fake_redis

    monkeypatch.setattr(cache_service.importlib, "import_module", fake_import_module)

    module = cache_service._load_redis_module()

    assert module is fake_redis


def test_load_redis_module_falls_back_to_project_venv(monkeypatch, tmp_path) -> None:
    """测试当前环境缺少 redis 时，会尝试加载项目 .venv 里的依赖。"""

    fake_redis = types.SimpleNamespace(__name__="redis")
    original_sys_path = list(sys.path)
    candidate_path = tmp_path / ".venv" / "lib" / "python3.13" / "site-packages"
    candidate_path.mkdir(parents=True)
    calls = {"count": 0}

    def fake_import_module(name: str):
        assert name == "redis"
        calls["count"] += 1
        if calls["count"] == 1:
            raise ImportError("missing redis")
        return fake_redis

    monkeypatch.setattr(cache_service.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(cache_service, "BACKEND_DIR", tmp_path)
    observed_path = {"value": None}

    try:
        module = cache_service._load_redis_module()
        observed_path["value"] = sys.path[0]
    finally:
        sys.path[:] = original_sys_path

    assert module is fake_redis
    assert calls["count"] == 2
    assert observed_path["value"] == str(candidate_path)


def test_load_redis_module_returns_none_when_everything_missing(monkeypatch, tmp_path) -> None:
    """测试当前环境和项目 .venv 都没有 redis 时，返回 None。"""

    monkeypatch.setattr(
        cache_service.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("missing redis")),
    )
    monkeypatch.setattr(cache_service, "BACKEND_DIR", tmp_path)

    assert cache_service._load_redis_module() is None
