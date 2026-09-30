from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.execution.cdp.plan_reader import CdpPlanReader
from app.services.action_planner import PlanSnapshot

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("/current", response_model=PlanSnapshot)
def current_plan(request: Request) -> PlanSnapshot:
    try:
        snapshot = CdpPlanReader(settings.cdp_endpoint).read_current()
        request.app.state.latest_plan_snapshot = snapshot
        return snapshot
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
