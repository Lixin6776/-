from copy import deepcopy

from app.execution.cdp.page_adapter import ActionAttempt, PlanPageSnapshot


class FakePageAdapter:
    def __init__(self, plans: dict[str, dict]) -> None:
        self.plans = deepcopy(plans)

    async def get_plan(self, plan_id: str) -> PlanPageSnapshot:
        plan = self.plans[plan_id]
        return PlanPageSnapshot(
            id=plan_id,
            name=str(plan.get("name", plan_id)),
            status=str(plan["status"]),
            budget=float(plan["budget"]),
        )

    async def pause_plan(self, plan_id: str) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        self.plans[plan_id]["status"] = "paused"
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=True, before=before, after=after)

    async def enable_plan(self, plan_id: str) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        self.plans[plan_id]["status"] = "active"
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=True, before=before, after=after)

    async def update_plan_budget(self, plan_id: str, budget: float) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        self.plans[plan_id]["budget"] = float(budget)
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=True, before=before, after=after)