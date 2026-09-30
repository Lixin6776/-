import inspect
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_plan_snapshot
from app.models import ExecutionJob
from app.schemas import ExecutionJobRead, PendingConfirmationRead
from app.services.action_planner import ActionPlanner, ActionPreview, PlanSnapshot
from app.services.action_registry import ActionEnvelope, ActionName
from app.services.confirmations import ConfirmationService
from app.services.execution import ExecutionService
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/actions", tags=["actions"])
def _load_plan_for_action(request: Request, action: ActionEnvelope) -> PlanSnapshot:
    if action.action_name == ActionName.CREATE_PLAN:
        return PlanSnapshot(
            id=action.target_id,
            name=str(action.params.get("name", "新计划")),
            status="new",
            budget=0,
        )
    return _load_plan_or_missing(request, action.target_id)

def _load_plan_or_missing(request: Request, target_id: str) -> PlanSnapshot:
    try:
        return get_plan_snapshot(request, target_id)
    except (KeyError, ValueError):
        return PlanSnapshot(
            id=target_id,
            name="未知计划",
            status="missing",
            budget=0,
        )


class ActionPreviewRequest(BaseModel):
    action: ActionEnvelope


class ActionConfirmationRequest(BaseModel):
    action: ActionEnvelope


class BatchActionRequest(BaseModel):
    actions: list[ActionEnvelope]


@router.post("/preview", response_model=ActionPreview)
def preview_action(
    payload: ActionPreviewRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ActionPreview:
    profile = StrategyProfileService(db).get_active()
    snapshot = _load_plan_for_action(request, payload.action)
    return ActionPlanner().preflight(payload.action, profile, snapshot)


@router.post(
    "/confirmations",
    response_model=PendingConfirmationRead,
    status_code=201,
)
def create_action_confirmation(
    payload: ActionConfirmationRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    profile = StrategyProfileService(db).get_active()
    snapshot = _load_plan_for_action(request, payload.action)
    preview = ActionPlanner().preflight(payload.action, profile, snapshot)
    if not preview.allowed:
        raise HTTPException(status_code=409, detail=preview.blockers)
    return ConfirmationService(db).create_from_preview(preview)


@router.post("/batch-preview", response_model=list[ActionPreview])
def batch_preview(
    payload: BatchActionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    profile = StrategyProfileService(db).get_active()
    plans = {
        action.target_id: _load_plan_or_missing(request, action.target_id)
        for action in payload.actions
    }
    return ActionPlanner().preflight_batch(payload.actions, profile, plans)


@router.post(
    "/batch-confirmations",
    response_model=list[PendingConfirmationRead],
    status_code=201,
)
def batch_confirmations(
    payload: BatchActionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    profile = StrategyProfileService(db).get_active()
    plans = {
        action.target_id: _load_plan_or_missing(request, action.target_id)
        for action in payload.actions
    }
    previews = ActionPlanner().preflight_batch(payload.actions, profile, plans)
    if any(not preview.allowed for preview in previews):
        raise HTTPException(status_code=409, detail="Batch preflight failed")
    service = ConfirmationService(db)
    return [service.create_from_preview(preview) for preview in previews]


@router.post(
    "/confirmations/{confirmation_id}/execute",
    response_model=ExecutionJobRead,
    status_code=202,
)
async def execute_confirmation(
    confirmation_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    confirmation_service = ConfirmationService(db)
    confirmation = confirmation_service.get(confirmation_id)
    if confirmation is None:
        raise HTTPException(status_code=404, detail="Confirmation not found")

    existing = db.scalar(
        select(ExecutionJob).where(ExecutionJob.confirmation_id == confirmation_id)
    )
    if existing is not None and existing.status in ExecutionService.TERMINAL_STATUSES:
        return existing

    provider_factory = getattr(request.app.state, "execution_provider_factory", None)
    if provider_factory is None:
        raise HTTPException(status_code=503, detail="Execution provider is not configured")
    try:
        provider, close = await provider_factory()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        service = ExecutionService(provider, confirmation_service, db)
        record = await service.run_confirmation(confirmation_id)
    finally:
        close_result = close()
        if inspect.isawaitable(close_result):
            await close_result

    job = db.get(ExecutionJob, record.job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Execution job was not persisted")
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