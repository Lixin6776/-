import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class StrategyProfile(Base):
    __tablename__ = "strategy_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    business_direction: Mapped[str] = mapped_column(String(120), nullable=False)
    primary_objective: Mapped[str] = mapped_column(String(500), nullable=False)
    secondary_objectives: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    hard_constraints: Mapped[dict] = mapped_column(JSON, nullable=False)
    monitoring_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    allowed_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    notification_policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)