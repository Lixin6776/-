from enum import StrEnum

from pydantic import BaseModel, Field


class ActionName(StrEnum):
    PAUSE_PLAN = "pause_plan"
    ENABLE_PLAN = "enable_plan"
    UPDATE_PLAN_BUDGET = "update_plan_budget"


class PausePlanInput(BaseModel):
    target_id: str = Field(min_length=1)


class EnablePlanInput(BaseModel):
    target_id: str = Field(min_length=1)


class UpdatePlanBudgetInput(BaseModel):
    target_id: str = Field(min_length=1)
    budget: float = Field(gt=0)


class ActionEnvelope(BaseModel):
    action_name: ActionName
    target_id: str = Field(min_length=1)
    params: dict = {}


class ActionDefinition(BaseModel):
    name: ActionName
    description: str
    scope: str
    input_model: type[BaseModel]
    confirmation_fields: tuple[str, ...]
    verification_method: str


class ActionRegistry:
    def __init__(self, definitions: dict[ActionName, ActionDefinition]) -> None:
        self._definitions = definitions

    @classmethod
    def default(cls) -> "ActionRegistry":
        return cls(
            {
                ActionName.PAUSE_PLAN: ActionDefinition(
                    name=ActionName.PAUSE_PLAN,
                    description="暂停一个正在投放的计划",
                    scope="plan",
                    input_model=PausePlanInput,
                    confirmation_fields=("target_id", "status"),
                    verification_method="read_plan_status",
                ),
                ActionName.ENABLE_PLAN: ActionDefinition(
                    name=ActionName.ENABLE_PLAN,
                    description="启用一个已暂停的计划",
                    scope="plan",
                    input_model=EnablePlanInput,
                    confirmation_fields=("target_id", "status"),
                    verification_method="read_plan_status",
                ),
                ActionName.UPDATE_PLAN_BUDGET: ActionDefinition(
                    name=ActionName.UPDATE_PLAN_BUDGET,
                    description="修改计划预算",
                    scope="plan",
                    input_model=UpdatePlanBudgetInput,
                    confirmation_fields=("target_id", "budget"),
                    verification_method="read_plan_budget",
                ),
            }
        )

    def get(self, name: ActionName | str) -> ActionDefinition:
        try:
            action_name = ActionName(name)
        except ValueError as exc:
            raise KeyError(f"Unknown action: {name}") from exc
        if action_name not in self._definitions:
            raise KeyError(f"Unknown action: {name}")
        return self._definitions[action_name]