from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.confirmations import PendingConfirmation
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


class ConfirmationCreate(BaseModel):
    recommendation_id: str
    action: dict
    profile_version: int


@router.post("/confirmations", response_model=PendingConfirmation, status_code=201)
def create_confirmation(
    payload: ConfirmationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> PendingConfirmation:
    profile = StrategyProfileService(db).get_active()
    if profile.version != payload.profile_version:
        raise HTTPException(status_code=409, detail="Strategy profile version changed")
    return request.app.state.confirmation_service.create(
        recommendation_id=payload.recommendation_id,
        action=payload.action,
        profile=profile,
    )