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