from collections.abc import Callable

from fastapi import HTTPException, Request

from app.services.action_planner import PlanSnapshot


def get_plan_snapshot(request: Request, target_id: str) -> PlanSnapshot:
    provider: Callable[[str], PlanSnapshot] | None = getattr(
        request.app.state,
        "plan_snapshot_provider",
        None,
    )
    if provider is None:
        raise HTTPException(status_code=503, detail="Plan snapshot provider is not configured")
    return provider(target_id)