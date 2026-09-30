import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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

class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recommendation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action_name: Mapped[str] = mapped_column(String(80), nullable=False)
    action_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    preview_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionJob(Base):
    __tablename__ = "execution_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    confirmation_id: Mapped[str] = mapped_column(
        ForeignKey("pending_confirmations.id"), nullable=False, index=True
    )
    action_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    artifact_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class LearningCase(Base):
    __tablename__ = "learning_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confirmation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    execution_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action_name: Mapped[str] = mapped_column(String(80), nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="observed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionOutcome(Base):
    __tablename__ = "decision_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(ForeignKey("learning_cases.id"), nullable=False, index=True)
    metric_window: Mapped[str] = mapped_column(String(16), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StrategyEvaluation(Base):
    __tablename__ = "strategy_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    effect_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StrategySuggestion(Base):
    __tablename__ = "strategy_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    suggestion_type: Mapped[str] = mapped_column(String(40), nullable=False)
    proposed_change: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
