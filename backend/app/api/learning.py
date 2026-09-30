from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    LearningCase,
    StrategyEvaluation,
    StrategyProfile,
    StrategySuggestion,
)
from app.schemas import (
    LearningCaseRead,
    StrategyEvaluationRead,
    StrategySuggestionRead,
)
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/learning", tags=["learning"])


class SuggestionDecision(BaseModel):
    reason: str = ""


@router.get("/cases", response_model=list[LearningCaseRead])
def list_cases(db: Annotated[Session, Depends(get_db)]):
    return list(db.scalars(select(LearningCase).order_by(LearningCase.created_at.desc())))


@router.get("/cases/{case_id}", response_model=LearningCaseRead)
def get_case(case_id: str, db: Annotated[Session, Depends(get_db)]):
    case = db.get(LearningCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Learning case not found")
    return case


@router.get("/evaluations", response_model=list[StrategyEvaluationRead])
def list_evaluations(db: Annotated[Session, Depends(get_db)]):
    return list(
        db.scalars(select(StrategyEvaluation).order_by(StrategyEvaluation.created_at.desc()))
    )


@router.get("/suggestions", response_model=list[StrategySuggestionRead])
def list_suggestions(db: Annotated[Session, Depends(get_db)]):
    return list(
        db.scalars(select(StrategySuggestion).order_by(StrategySuggestion.created_at.desc()))
    )


@router.post("/suggestions/{suggestion_id}/accept", response_model=StrategySuggestionRead)
def accept_suggestion(
    suggestion_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    suggestion = db.get(StrategySuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    active = StrategyProfileService(db).get_active()
    draft = StrategyProfile(
        version=active.version + 1,
        name=f"{active.name} - learning draft",
        business_direction=active.business_direction,
        primary_objective=active.primary_objective,
        secondary_objectives=active.secondary_objectives,
        hard_constraints={
            **active.hard_constraints,
            "learning_adjustments": suggestion.proposed_change,
        },
        monitoring_config=active.monitoring_config,
        allowed_actions=active.allowed_actions,
        notification_policy=active.notification_policy,
        active=False,
    )
    suggestion.status = "accepted"
    db.add(draft)
    db.commit()
    db.refresh(suggestion)
    return suggestion


@router.post("/suggestions/{suggestion_id}/reject", response_model=StrategySuggestionRead)
def reject_suggestion(
    suggestion_id: str,
    payload: SuggestionDecision,
    db: Annotated[Session, Depends(get_db)],
):
    suggestion = db.get(StrategySuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    suggestion.status = "rejected"
    suggestion.evidence = {**suggestion.evidence, "rejection_reason": payload.reason}
    db.commit()
    db.refresh(suggestion)
    return suggestion