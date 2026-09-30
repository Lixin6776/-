from copy import deepcopy

from app.execution.base import (
    CancelResult,
    ExecutionResult,
    PreflightResult,
    VerificationResult,
)
from app.services.action_registry import ActionEnvelope, ActionName


class FakeExecutionProvider:
    def __init__(self, initial_plan: dict) -> None:
        self.plans = {str(initial_plan["id"]): deepcopy(initial_plan)}
        self.execute_calls = 0

    async def preflight(self, action: ActionEnvelope) -> PreflightResult:
        plan = self.plans.get(action.target_id)
        if plan is None:
            return PreflightResult(ok=False, before={}, message="Plan not found")
        return PreflightResult(ok=True, before=deepcopy(plan))

    async def execute(self, action: ActionEnvelope) -> ExecutionResult:
        self.execute_calls += 1
        plan = self.plans[action.target_id]
        before = deepcopy(plan)
        if action.action_name == ActionName.PAUSE_PLAN:
            plan["status"] = "paused"
        elif action.action_name == ActionName.ENABLE_PLAN:
            plan["status"] = "active"
        elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            plan["budget"] = float(action.params["budget"])
        after = deepcopy(plan)
        return ExecutionResult(
            action={
                "action_name": action.action_name.value,
                "target_id": action.target_id,
                "params": action.params,
            },
            before=before,
            after=after,
        )

    async def verify(
        self,
        action: ActionEnvelope,
        result: ExecutionResult,
    ) -> VerificationResult:
        expected = deepcopy(result.after)
        if action.action_name == ActionName.PAUSE_PLAN:
            expected["status"] = "paused"
        elif action.action_name == ActionName.ENABLE_PLAN:
            expected["status"] = "active"
        elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            expected["budget"] = float(action.params["budget"])
        ok = self.plans[action.target_id] == expected
        return VerificationResult(
            ok=ok,
            before=result.before,
            after=deepcopy(self.plans[action.target_id]),
            message="verified" if ok else "state mismatch",
        )

    async def cancel(self, job_id: str) -> CancelResult:
        return CancelResult(cancelled=False, message=f"Job {job_id} is already synchronous")