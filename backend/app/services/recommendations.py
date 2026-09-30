from pydantic import BaseModel

from app.models import StrategyProfile
from app.services.changes import ChangeLevel, ChangeSignal


class Recommendation(BaseModel):
    reason: str
    action: str
    confidence: str
    strategy_profile_version: int
    requires_confirmation: bool = True


class RecommendationEngine:
    def recommend(self, signal: ChangeSignal, profile: StrategyProfile) -> Recommendation | None:
        if signal.level != ChangeLevel.ACTION:
            return None
        if "update_plan_budget" not in profile.allowed_actions:
            return None
        return Recommendation(
            reason=f"{signal.reason}；必须人工确认后执行。",
            action="update_plan_budget",
            confidence="medium",
            strategy_profile_version=profile.version,
        )