from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ExecutionJob
from app.schemas import ExecutionJobRead
from app.services.action_planner import ActionPlanner, ActionPreview, PlanSnapshot
from app.services.action_registry import ActionEnvelope
from app.services.confirmations import ConfirmationService
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/actions", tags=["actions"])


class ActionPreviewRequest(BaseModel):
    action: ActionEnvelope


def get_plan_snapshot(request: Request, target_id: str) -> PlanSnapshot:
    provider: Callable[[str], PlanSnapshot] | None = getattr(
        request.app.state,
        "plan_snapshot_provider",
        None,
    )
    if provider is None:
        raise HTTPException(status_code=503, detail="Plan snapshot provider is not configured")
    return provider(target_id)


@router.post("/preview", response_model=ActionPreview)
def preview_action(
    payload: ActionPreviewRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ActionPreview:
    profile = StrategyProfileService(db).get_active()
    snapshot = get_plan_snapshot(request, payload.action.target_id)
    return ActionPlanner().preflight(payload.action, profile, snapshot)


@router.post(
    "/confirmations/{confirmation_id}/execute",
    response_model=ExecutionJobRead,
    status_code=202,
)
def execute_confirmation(
    confirmation_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    confirmation_service = ConfirmationService(db)
    confirmation = confirmation_service.get(confirmation_id)
    if confirmation is None:
        raise HTTPException(status_code=404, detail="Confirmation not found")

    existing = db.scalar(
        select(ExecutionJob).where(ExecutionJob.confirmation_id == confirmation_id)
    )
    if existing is not None:
        return existing

    if not confirmation_service.claim(confirmation_id):
        raise HTTPException(status_code=409, detail="Confirmation is not executable")

    job = ExecutionJob(
        confirmation_id=confirmation.id,
        action_name=confirmation.action_name,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs", response_model=list[ExecutionJobRead])
def list_jobs(db: Annotated[Session, Depends(get_db)]):
    return list(db.scalars(select(ExecutionJob).order_by(ExecutionJob.created_at.desc())))


@router.get("/jobs/{job_id}", response_model=ExecutionJobRead)
def get_job(job_id: str, db: Annotated[Session, Depends(get_db)]):
    job = db.get(ExecutionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Execution job not found")
    return job