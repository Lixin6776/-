from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LearningCase


class CaseQuery(BaseModel):
    business_direction: str
    primary_objective: str
    action_name: str
    plan_stage: str | None = None
    product_category: str | None = None
    hour: int | None = None
    spend: float | None = None
    roi: float | None = None


@dataclass(frozen=True)
class CaseMatch:
    case: LearningCase
    score: float
    matched_reasons: list[str]


class CaseLibrary:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_similar(self, query: CaseQuery, limit: int = 5) -> list[CaseMatch]:
        cases = list(self.session.scalars(select(LearningCase)))
        matches = [self._score(query, case) for case in cases]
        return sorted(matches, key=lambda match: match.score, reverse=True)[:limit]

    @staticmethod
    def _score(query: CaseQuery, case: LearningCase) -> CaseMatch:
        context = case.context
        score = 0.0
        reasons: list[str] = []
        if context.get("business_direction") == query.business_direction:
            score += 0.25
            reasons.append("business_direction")
        if context.get("primary_objective") == query.primary_objective:
            score += 0.2
            reasons.append("primary_objective")
        if case.action_name == query.action_name:
            score += 0.2
            reasons.append("action_name")
        if query.plan_stage and context.get("plan_stage") == query.plan_stage:
            score += 0.1
            reasons.append("plan_stage")
        if query.product_category and context.get("product_category") == query.product_category:
            score += 0.05
            reasons.append("product_category")
        if query.hour is not None and context.get("hour") is not None:
            score += max(0.0, 0.1 - abs(int(context["hour"]) - query.hour) / 24)
        if query.spend is not None and context.get("spend") is not None:
            distance = abs(float(context["spend"]) - query.spend) / max(query.spend, 1)
            score += max(0.0, 0.05 - distance * 0.05)
        if query.roi is not None and context.get("roi") is not None:
            distance = abs(float(context["roi"]) - query.roi) / max(abs(query.roi), 1)
            score += max(0.0, 0.05 - distance * 0.05)
        return CaseMatch(case=case, score=round(min(score, 1.0), 10), matched_reasons=reasons)