from __future__ import annotations

import os
import tempfile
from pathlib import Path


TEST_DB_PATH = Path(tempfile.gettempdir()) / f"trip_planner_test_{os.getpid()}.db"
os.environ["SQLITE_DB_PATH"] = str(TEST_DB_PATH)


def pytest_sessionstart(session) -> None:  # noqa: ANN001
    """确保测试使用独立 SQLite 数据库，避免污染本地开发历史记录。"""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    """测试结束后清理临时 SQLite 数据库。"""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
