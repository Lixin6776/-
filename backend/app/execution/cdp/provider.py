import asyncio
from typing import ClassVar, Protocol

from app.execution.base import (
    CancelResult,
    ExecutionResult,
    PreflightResult,
    VerificationResult,
)
from app.execution.cdp.page_adapter import ActionAttempt, PlanPageSnapshot
from app.services.action_registry import ActionEnvelope, ActionName


class PageAdapter(Protocol):
    async def get_plan(self, plan_id: str) -> PlanPageSnapshot:
        ...

    async def pause_plan(self, plan_id: str) -> ActionAttempt:
        ...

    async def enable_plan(self, plan_id: str) -> ActionAttempt:
        ...

    async def update_plan_budget(self, plan_id: str, budget: float) -> ActionAttempt:
        ...


class CdpExecutionProvider:
    _write_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self, adapter: PageAdapter) -> None:
        self.adapter = adapter

    async def preflight(self, action: ActionEnvelope) -> PreflightResult:
        try:
            plan = await self.adapter.get_plan(action.target_id)
        except (KeyError, ValueError) as exc:
            return PreflightResult(ok=False, before={}, message=str(exc))
        return PreflightResult(ok=True, before=plan.model_dump())

    async def execute(self, action: ActionEnvelope) -> ExecutionResult:
        async with self._write_lock:
            if action.action_name == ActionName.PAUSE_PLAN:
                attempt = await self.adapter.pause_plan(action.target_id)
            elif action.action_name == ActionName.ENABLE_PLAN:
                attempt = await self.adapter.enable_plan(action.target_id)
            elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
                attempt = await self.adapter.update_plan_budget(
                    action.target_id,
                    float(action.params["budget"]),
                )
            else:
                raise KeyError(f"Unsupported action: {action.action_name}")
            return ExecutionResult(
                action={
                    "action_name": action.action_name.value,
                    "target_id": action.target_id,
                    "params": action.params,
                },
                before=attempt.before,
                after=attempt.after,
                message=attempt.message,
            )

    async def verify(
        self,
        action: ActionEnvelope,
        result: ExecutionResult,
    ) -> VerificationResult:
        current = (await self.adapter.get_plan(action.target_id)).model_dump()
        expected = dict(result.after)
        if action.action_name == ActionName.PAUSE_PLAN:
            expected["status"] = "paused"
        elif action.action_name == ActionName.ENABLE_PLAN:
            expected["status"] = "active"
        elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            expected["budget"] = float(action.params["budget"])
        return VerificationResult(
            ok=current == expected,
            before=result.before,
            after=current,
            message="verified" if current == expected else "state mismatch",
        )

    async def cancel(self, job_id: str) -> CancelResult:
        return CancelResult(cancelled=False, message=f"Job {job_id} is not cancellable")