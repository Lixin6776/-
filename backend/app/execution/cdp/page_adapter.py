import json
from typing import Any

from pydantic import BaseModel, Field

from app.execution.cdp.selector_config import SelectorConfig
from app.services.action_registry import ActionEnvelope


class PlanPageSnapshot(BaseModel):
    id: str
    name: str
    status: str
    budget: float
    bid: float | None = None
    targeting: dict = Field(default_factory=dict)
    schedule: dict = Field(default_factory=dict)
    materials: list[str] = Field(default_factory=list)
    available_materials: list[str] = Field(default_factory=list)


class ActionAttempt(BaseModel):
    ok: bool
    before: dict
    after: dict
    message: str = ""


class QianchuanPageAdapter:
    def __init__(self, page: Any, config: SelectorConfig) -> None:
        self.page = page
        self.config = config

    def _row(self, plan_id: str):
        return self.page.locator(self.config.plan_rows).filter(has_text=plan_id).first

    async def get_plan(self, plan_id: str) -> PlanPageSnapshot:
        row = self._row(plan_id)
        return PlanPageSnapshot(
            id=await row.locator(self.config.plan_id).inner_text(),
            name=await row.locator(self.config.plan_name).inner_text(),
            status=(await row.locator(self.config.plan_status).inner_text()).strip(),
            budget=float(
                (await row.locator(self.config.budget_value).inner_text())
                .replace("¥", "")
                .replace(",", "")
                .strip()
            ),
        )

    async def pause_plan(self, plan_id: str) -> ActionAttempt:
        return await self._toggle_status(plan_id, "paused")

    async def enable_plan(self, plan_id: str) -> ActionAttempt:
        return await self._toggle_status(plan_id, "active")

    async def update_plan_budget(self, plan_id: str, budget: float) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        row = self._row(plan_id)
        await row.locator(self.config.budget_edit_button).click()
        await row.locator(self.config.budget_input).fill(str(budget))
        await row.locator(self.config.budget_save_button).click()
        await self._submit_confirmation_if_present()
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=float(after["budget"]) == float(budget), before=before, after=after)

    async def create_plan(self, action: ActionEnvelope) -> ActionAttempt:
        await self.page.locator(self.config.create_plan_button).click()
        await self.page.locator(self.config.plan_form_name).fill(action.params["name"])
        await self.page.locator(self.config.plan_form_budget).fill(str(action.params["budget"]))
        await self.page.locator(self.config.plan_form_roi_goal).fill(str(action.params["roi_goal"]))
        await self.page.locator(self.config.plan_form_submit).click()
        await self._submit_confirmation_if_present()
        return ActionAttempt(ok=True, before={}, after=action.params)

    async def copy_plan(self, action: ActionEnvelope) -> ActionAttempt:
        before = (await self.get_plan(action.target_id)).model_dump()
        row = self._row(action.target_id)
        await row.locator(self.config.copy_plan_button).click()
        await self.page.locator(self.config.plan_form_name).fill(action.params["name"])
        await self.page.locator(self.config.plan_form_submit).click()
        await self._submit_confirmation_if_present()
        after = dict(before)
        after["name"] = action.params["name"]
        return ActionAttempt(ok=True, before=before, after=after)

    async def delete_plan(self, action: ActionEnvelope) -> ActionAttempt:
        before = (await self.get_plan(action.target_id)).model_dump()
        await self._row(action.target_id).locator(self.config.delete_plan_button).click()
        await self.page.locator(self.config.delete_confirm_input).fill(action.target_id)
        await self.page.locator(self.config.delete_confirm_submit).click()
        return ActionAttempt(ok=True, before=before, after={"deleted": True})

    async def edit_plan(self, action: ActionEnvelope) -> ActionAttempt:
        before = (await self.get_plan(action.target_id)).model_dump()
        row = self._row(action.target_id)
        await row.locator(self.config.edit_plan_button).click()
        for key, value in action.params["fields"].items():
            await row.locator(self.config.edit_field_container).locator(f'[name="{key}"]').fill(str(value))
        await self.page.locator(self.config.plan_form_submit).click()
        await self._submit_confirmation_if_present()
        after = {**before, **action.params["fields"]}
        return ActionAttempt(ok=True, before=before, after=after)

    async def update_bid(self, action: ActionEnvelope) -> ActionAttempt:
        return await self._fill_and_save(action, self.config.bid_input, {"bid": float(action.params["bid"])})

    async def update_targeting(self, action: ActionEnvelope) -> ActionAttempt:
        return await self._fill_and_save(
            action,
            self.config.targeting_editor,
            {"targeting": action.params["targeting"]},
        )

    async def update_schedule(self, action: ActionEnvelope) -> ActionAttempt:
        return await self._fill_and_save(
            action,
            self.config.schedule_editor,
            {"schedule": action.params["schedule"]},
        )

    async def bind_material(self, action: ActionEnvelope) -> ActionAttempt:
        before = (await self.get_plan(action.target_id)).model_dump()
        await self.page.locator(self.config.material_picker).fill(action.params["material_id"])
        await self.page.locator(self.config.material_bind_button).click()
        await self._submit_confirmation_if_present()
        after = {**before, "materials": [*before.get("materials", []), action.params["material_id"]]}
        return ActionAttempt(ok=True, before=before, after=after)

    async def unbind_material(self, action: ActionEnvelope) -> ActionAttempt:
        before = (await self.get_plan(action.target_id)).model_dump()
        await self.page.locator(self.config.material_picker).fill(action.params["material_id"])
        await self.page.locator(self.config.material_unbind_button).click()
        await self._submit_confirmation_if_present()
        after = {
            **before,
            "materials": [
                item for item in before.get("materials", []) if item != action.params["material_id"]
            ],
        }
        return ActionAttempt(ok=True, before=before, after=after)

    async def _toggle_status(self, plan_id: str, status: str) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        await self._row(plan_id).locator(self.config.plan_status_toggle).click()
        await self._submit_confirmation_if_present()
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=after["status"] == status, before=before, after=after)

    async def _fill_and_save(
        self,
        action: ActionEnvelope,
        selector: str,
        changed: dict,
    ) -> ActionAttempt:
        before = (await self.get_plan(action.target_id)).model_dump()
        row = self._row(action.target_id)
        await row.locator(self.config.edit_plan_button).click()
        value = changed[next(iter(changed))]
        serialized = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        await row.locator(selector).fill(serialized)
        await self.page.locator(self.config.plan_form_submit).click()
        await self._submit_confirmation_if_present()
        return ActionAttempt(ok=True, before=before, after={**before, **changed})

    async def _submit_confirmation_if_present(self) -> None:
        dialog = self.page.locator(self.config.confirmation_dialog)
        if await dialog.is_visible():
            await dialog.locator(self.config.confirmation_submit).click()