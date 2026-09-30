from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import StrategyProfileCreate, StrategyProfileRead
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("/versions", response_model=StrategyProfileRead, status_code=201)
def create_profile(payload: StrategyProfileCreate, db: Session = Depends(get_db)):
    return StrategyProfileService(db).create_version(payload)


@router.get("/active", response_model=StrategyProfileRead)
def active_profile(db: Session = Depends(get_db)):
    try:
        return StrategyProfileService(db).get_active()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc