from typing import Any

from pydantic import BaseModel

from app.execution.cdp.selector_config import SelectorConfig


class PlanPageSnapshot(BaseModel):
    id: str
    name: str
    status: str
    budget: float


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
        before = (await self.get_plan(plan_id)).model_dump()
        await self._row(plan_id).locator(self.config.plan_status_toggle).click()
        await self._submit_confirmation_if_present()
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=after["status"] == "paused", before=before, after=after)

    async def enable_plan(self, plan_id: str) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        await self._row(plan_id).locator(self.config.plan_status_toggle).click()
        await self._submit_confirmation_if_present()
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(ok=after["status"] == "active", before=before, after=after)

    async def update_plan_budget(self, plan_id: str, budget: float) -> ActionAttempt:
        before = (await self.get_plan(plan_id)).model_dump()
        row = self._row(plan_id)
        await row.locator(self.config.budget_edit_button).click()
        await row.locator(self.config.budget_input).fill(str(budget))
        await row.locator(self.config.budget_save_button).click()
        await self._submit_confirmation_if_present()
        after = (await self.get_plan(plan_id)).model_dump()
        return ActionAttempt(
            ok=float(after["budget"]) == float(budget),
            before=before,
            after=after,
        )

    async def _submit_confirmation_if_present(self) -> None:
        dialog = self.page.locator(self.config.confirmation_dialog)
        if await dialog.is_visible():
            await dialog.locator(self.config.confirmation_submit).click()