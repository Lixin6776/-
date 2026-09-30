from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrategyProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    business_direction: str = Field(min_length=1, max_length=120)
    primary_objective: str = Field(min_length=1, max_length=500)
    secondary_objectives: list[str] = []
    hard_constraints: dict = {}
    monitoring_config: dict = {"interval_minutes": 5}
    allowed_actions: list[str] = []
    notification_policy: dict = {"dedupe_minutes": 10}


class StrategyProfileRead(StrategyProfileCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    active: bool
    created_at: datetime
    effective_at: datetime

class PendingConfirmationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recommendation_id: str | None
    action_name: str
    action_params: dict
    preview_hash: str
    strategy_profile_version: int
    idempotency_key: str
    status: str
    expires_at: datetime
    created_at: datetime
    claimed_at: datetime | None
    executed_at: datetime | None


class ExecutionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    confirmation_id: str
    action_name: str
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    result: dict

class LearningCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_profile_version: int
    recommendation_id: str | None
    confirmation_id: str | None
    execution_job_id: str | None
    action_name: str
    context: dict
    status: str
    created_at: datetime


class DecisionOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    metric_window: str
    metrics: dict
    observed_at: datetime


class StrategyEvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str | None
    sample_size: int
    effect_size: float | None
    confidence: str
    verdict: str
    evidence: dict
    created_at: datetime


class StrategySuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_profile_version: int
    suggestion_type: str
    proposed_change: dict
    evidence: dict
    confidence: str
    status: str
    created_at: datetime
