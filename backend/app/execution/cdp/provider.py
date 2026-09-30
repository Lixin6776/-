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

    async def create_plan(self, action: ActionEnvelope) -> ActionAttempt:
        ...

    async def copy_plan(self, action: ActionEnvelope) -> ActionAttempt:
        ...

    async def delete_plan(self, action: ActionEnvelope) -> ActionAttempt:
        ...

    async def edit_plan(self, action: ActionEnvelope) -> ActionAttempt:
        ...

    async def update_bid(self, action: ActionEnvelope) -> ActionAttempt:
        ...

    async def update_targeting(self, action: ActionEnvelope) -> ActionAttempt:
        ...

    async def update_schedule(self, action: ActionEnvelope) -> ActionAttempt:
        ...

    async def bind_material(self, action: ActionEnvelope) -> ActionAttempt:
        ...

    async def unbind_material(self, action: ActionEnvelope) -> ActionAttempt:
        ...


class CdpExecutionProvider:
    _write_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self, adapter: PageAdapter) -> None:
        self.adapter = adapter

    async def preflight(self, action: ActionEnvelope) -> PreflightResult:
        if action.action_name == ActionName.CREATE_PLAN:
            return PreflightResult(ok=True, before={})
        try:
            plan = await self.adapter.get_plan(action.target_id)
        except (KeyError, ValueError) as exc:
            return PreflightResult(ok=False, before={}, message=str(exc))
        return PreflightResult(ok=True, before=plan.model_dump())

    async def execute(self, action: ActionEnvelope) -> ExecutionResult:
        async with self._write_lock:
            attempt = await self._execute_attempt(action)
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
        if action.action_name in {ActionName.CREATE_PLAN, ActionName.COPY_PLAN}:
            target_id = str(result.after["id"])
            try:
                current = (await self.adapter.get_plan(target_id)).model_dump()
                ok = current["name"] == action.params["name"]
            except KeyError:
                current = {}
                ok = False
            return VerificationResult(ok=ok, before=result.before, after=current)
        if action.action_name == ActionName.DELETE_PLAN:
            try:
                current = (await self.adapter.get_plan(action.target_id)).model_dump()
                ok = False
            except KeyError:
                current = {"deleted": True}
                ok = True
            return VerificationResult(ok=ok, before=result.before, after=current)

        try:
            current = (await self.adapter.get_plan(action.target_id)).model_dump()
        except KeyError as exc:
            return VerificationResult(
                ok=False,
                before=result.before,
                after={},
                message=str(exc),
            )
        expected = dict(current)
        if action.action_name == ActionName.PAUSE_PLAN:
            expected["status"] = "paused"
        elif action.action_name == ActionName.ENABLE_PLAN:
            expected["status"] = "active"
        elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            expected["budget"] = float(action.params["budget"])
        elif action.action_name == ActionName.EDIT_PLAN:
            expected.update(action.params["fields"])
        elif action.action_name == ActionName.UPDATE_PLAN_BID:
            expected["bid"] = float(action.params["bid"])
        elif action.action_name == ActionName.UPDATE_TARGETING:
            expected["targeting"] = action.params["targeting"]
        elif action.action_name == ActionName.UPDATE_SCHEDULE:
            expected["schedule"] = action.params["schedule"]
        elif action.action_name == ActionName.BIND_EXISTING_MATERIAL:
            expected["materials"] = [*current.get("materials", []), action.params["material_id"]]
        elif action.action_name == ActionName.UNBIND_EXISTING_MATERIAL:
            expected["materials"] = [
                item for item in current.get("materials", []) if item != action.params["material_id"]
            ]
        return VerificationResult(
            ok=current == expected,
            before=result.before,
            after=current,
            message="verified" if current == expected else "state mismatch",
        )

    async def _execute_attempt(self, action: ActionEnvelope) -> ActionAttempt:
        if action.action_name == ActionName.PAUSE_PLAN:
            return await self.adapter.pause_plan(action.target_id)
        if action.action_name == ActionName.ENABLE_PLAN:
            return await self.adapter.enable_plan(action.target_id)
        if action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            return await self.adapter.update_plan_budget(action.target_id, float(action.params["budget"]))
        if action.action_name == ActionName.CREATE_PLAN:
            return await self.adapter.create_plan(action)
        if action.action_name == ActionName.COPY_PLAN:
            return await self.adapter.copy_plan(action)
        if action.action_name == ActionName.DELETE_PLAN:
            return await self.adapter.delete_plan(action)
        if action.action_name == ActionName.EDIT_PLAN:
            return await self.adapter.edit_plan(action)
        if action.action_name == ActionName.UPDATE_PLAN_BID:
            return await self.adapter.update_bid(action)
        if action.action_name == ActionName.UPDATE_TARGETING:
            return await self.adapter.update_targeting(action)
        if action.action_name == ActionName.UPDATE_SCHEDULE:
            return await self.adapter.update_schedule(action)
        if action.action_name == ActionName.BIND_EXISTING_MATERIAL:
            return await self.adapter.bind_material(action)
        if action.action_name == ActionName.UNBIND_EXISTING_MATERIAL:
            return await self.adapter.unbind_material(action)
        raise KeyError(f"Unsupported action: {action.action_name}")

    async def cancel(self, job_id: str) -> CancelResult:
        return CancelResult(cancelled=False, message=f"Job {job_id} is not cancellable")