from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[2]

DB_DIR = BACKEND_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

_sqlite_db_path_raw = Path(os.getenv("SQLITE_DB_PATH", str(DB_DIR / "app.db")))
SQLITE_DB_PATH = (
    _sqlite_db_path_raw
    if _sqlite_db_path_raw.is_absolute()
    else BACKEND_DIR / _sqlite_db_path_raw
)
SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH.as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
