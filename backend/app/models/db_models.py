from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow_naive() -> datetime:
    """Return UTC in the existing naive SQLite representation without deprecated utcnow()."""
    return datetime.now(UTC).replace(tzinfo=None)


class TripRecord(Base):
    """快速行程与深度规划任务共用的持久化记录。"""

    __tablename__ = "trip_records"

    # 数据库内部主键
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 业务侧使用的 itinerary 标识
    trip_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    destination: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    plan_type: Mapped[str] = mapped_column(String(20), default="quick")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    progress: Mapped[int] = mapped_column(Integer, default=100)
    display_title: Mapped[str] = mapped_column(Text, default="")
    detail_title: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deep_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 快速规划保存完整 itinerary；深度规划占位记录使用空 JSON 对象。
    itinerary_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow_naive,
        onupdate=_utcnow_naive,
    )
