from fastapi import APIRouter, HTTPException

from app.config import settings
from app.execution.cdp.plan_reader import CdpPlanReader
from app.services.action_planner import PlanSnapshot

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("/current", response_model=PlanSnapshot)
def current_plan() -> PlanSnapshot:
    try:
        return CdpPlanReader(settings.cdp_endpoint).read_current()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
