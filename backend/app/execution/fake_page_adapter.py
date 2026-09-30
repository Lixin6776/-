from copy import deepcopy

from app.execution.cdp.page_adapter import ActionAttempt, PlanPageSnapshot
from app.services.action_registry import ActionEnvelope


class FakePageAdapter:
    def __init__(self, plans: dict[str, dict]) -> None:
        self.plans = deepcopy(plans)
        self._next_plan_number = len(self.plans) + 1

    def _new_plan_id(self) -> str:
        plan_id = f"plan-{self._next_plan_number}"
        self._next_plan_number += 1
        return plan_id

    async def get_plan(self, plan_id: str) -> PlanPageSnapshot:
        plan = self.plans[plan_id]
        return PlanPageSnapshot(
            id=plan_id,
            name=str(plan.get("name", plan_id)),
            status=str(plan["status"]),
            budget=float(plan["budget"]),
            bid=plan.get("bid"),
            targeting=dict(plan.get("targeting", {})),
            schedule=dict(plan.get("schedule", {})),
            materials=list(plan.get("materials", [])),
            available_materials=list(plan.get("available_materials", [])),
        )

    async def pause_plan(self, plan_id: str) -> ActionAttempt:
        return await self._set_status(plan_id, "paused")

    async def enable_plan(self, plan_id: str) -> ActionAttempt:
        return await self._set_status(plan_id, "active")

    async def update_plan_budget(self, plan_id: str, budget: float) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        self.plans[plan_id]["budget"] = float(budget)
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=True, before=before, after=after)

    async def create_plan(self, action: ActionEnvelope) -> ActionAttempt:
        target_id = self._new_plan_id()
        self.plans[target_id] = {
            "name": action.params["name"],
            "status": "active",
            "budget": float(action.params["budget"]),
            "bid": None,
            "targeting": {},
            "schedule": {},
            "materials": [],
            "available_materials": [],
            "roi_goal": float(action.params["roi_goal"]),
        }
        return ActionAttempt(ok=True, before={}, after=await self._snapshot(target_id))

    async def copy_plan(self, action: ActionEnvelope) -> ActionAttempt:
        source = deepcopy(self.plans[action.target_id])
        target_id = self._new_plan_id()
        source["name"] = action.params["name"]
        self.plans[target_id] = source
        return ActionAttempt(
            ok=True,
            before=await self._snapshot(action.target_id),
            after=await self._snapshot(target_id),
        )

    async def delete_plan(self, action: ActionEnvelope) -> ActionAttempt:
        before = await self._snapshot(action.target_id)
        del self.plans[action.target_id]
        return ActionAttempt(ok=True, before=before, after={"id": action.target_id, "deleted": True})

    async def edit_plan(self, action: ActionEnvelope) -> ActionAttempt:
        before = await self._snapshot(action.target_id)
        self.plans[action.target_id].update(action.params["fields"])
        return ActionAttempt(ok=True, before=before, after=await self._snapshot(action.target_id))

    async def update_bid(self, action: ActionEnvelope) -> ActionAttempt:
        before = await self._snapshot(action.target_id)
        self.plans[action.target_id]["bid"] = float(action.params["bid"])
        return ActionAttempt(ok=True, before=before, after=await self._snapshot(action.target_id))

    async def update_targeting(self, action: ActionEnvelope) -> ActionAttempt:
        before = await self._snapshot(action.target_id)
        self.plans[action.target_id]["targeting"] = deepcopy(action.params["targeting"])
        return ActionAttempt(ok=True, before=before, after=await self._snapshot(action.target_id))

    async def update_schedule(self, action: ActionEnvelope) -> ActionAttempt:
        before = await self._snapshot(action.target_id)
        self.plans[action.target_id]["schedule"] = deepcopy(action.params["schedule"])
        return ActionAttempt(ok=True, before=before, after=await self._snapshot(action.target_id))

    async def bind_material(self, action: ActionEnvelope) -> ActionAttempt:
        before = await self._snapshot(action.target_id)
        material_id = action.params["material_id"]
        self.plans[action.target_id].setdefault("materials", []).append(material_id)
        return ActionAttempt(ok=True, before=before, after=await self._snapshot(action.target_id))

    async def unbind_material(self, action: ActionEnvelope) -> ActionAttempt:
        before = await self._snapshot(action.target_id)
        material_id = action.params["material_id"]
        self.plans[action.target_id]["materials"] = [
            item for item in self.plans[action.target_id].get("materials", []) if item != material_id
        ]
        return ActionAttempt(ok=True, before=before, after=await self._snapshot(action.target_id))

    async def _set_status(self, plan_id: str, status: str) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        self.plans[plan_id]["status"] = status
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=True, before=before, after=after)

    async def _snapshot(self, plan_id: str) -> dict:
        return (await self.get_plan(plan_id)).model_dump()