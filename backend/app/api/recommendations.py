from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import PendingConfirmationRead
from app.services.confirmations import ConfirmationService
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


class ConfirmationCreate(BaseModel):
    recommendation_id: str
    action: dict
    profile_version: int


@router.post("/confirmations", response_model=PendingConfirmationRead, status_code=201)
def create_confirmation(
    payload: ConfirmationCreate,
    db: Annotated[Session, Depends(get_db)],
):
    profile = StrategyProfileService(db).get_active()
    if profile.version != payload.profile_version:
        raise HTTPException(status_code=409, detail="Strategy profile version changed")
    return ConfirmationService(db).create(
        recommendation_id=payload.recommendation_id,
        action=payload.action,
        profile=profile,
    )