from enum import StrEnum

from pydantic import BaseModel, Field


class ActionName(StrEnum):
    PAUSE_PLAN = "pause_plan"
    ENABLE_PLAN = "enable_plan"
    UPDATE_PLAN_BUDGET = "update_plan_budget"
    CREATE_PLAN = "create_plan"
    COPY_PLAN = "copy_plan"
    DELETE_PLAN = "delete_plan"
    EDIT_PLAN = "edit_plan"
    UPDATE_PLAN_BID = "update_plan_bid"
    UPDATE_TARGETING = "update_targeting"
    UPDATE_SCHEDULE = "update_schedule"
    BIND_EXISTING_MATERIAL = "bind_existing_material"
    UNBIND_EXISTING_MATERIAL = "unbind_existing_material"


class PausePlanInput(BaseModel):
    target_id: str = Field(min_length=1)


class EnablePlanInput(BaseModel):
    target_id: str = Field(min_length=1)


class UpdatePlanBudgetInput(BaseModel):
    target_id: str = Field(min_length=1)
    budget: float = Field(gt=0)


class CreatePlanInput(BaseModel):
    target_id: str = Field(min_length=1)
    source_product_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    budget: float = Field(gt=0)
    roi_goal: float = Field(gt=0)


class CopyPlanInput(BaseModel):
    target_id: str = Field(min_length=1)
    source_plan_id: str | None = None
    name: str = Field(min_length=1)


class DeletePlanInput(BaseModel):
    target_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EditPlanInput(BaseModel):
    target_id: str = Field(min_length=1)
    fields: dict = {}


class UpdatePlanBidInput(BaseModel):
    target_id: str = Field(min_length=1)
    bid: float = Field(gt=0)


class UpdateTargetingInput(BaseModel):
    target_id: str = Field(min_length=1)
    targeting: dict


class UpdateScheduleInput(BaseModel):
    target_id: str = Field(min_length=1)
    schedule: dict


class BindExistingMaterialInput(BaseModel):
    target_id: str = Field(min_length=1)
    material_id: str = Field(min_length=1)


class UnbindExistingMaterialInput(BaseModel):
    target_id: str = Field(min_length=1)
    material_id: str = Field(min_length=1)


class ActionEnvelope(BaseModel):
    action_name: ActionName
    target_id: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)


class ActionDefinition(BaseModel):
    name: ActionName
    description: str
    scope: str
    input_model: type[BaseModel]
    confirmation_fields: tuple[str, ...]
    verification_method: str
    destructive: bool = False


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
                ActionName.CREATE_PLAN: ActionDefinition(
                    name=ActionName.CREATE_PLAN,
                    description="创建投放计划",
                    scope="plan",
                    input_model=CreatePlanInput,
                    confirmation_fields=("name", "budget", "roi_goal"),
                    verification_method="read_created_plan",
                ),
                ActionName.COPY_PLAN: ActionDefinition(
                    name=ActionName.COPY_PLAN,
                    description="复制已有计划",
                    scope="plan",
                    input_model=CopyPlanInput,
                    confirmation_fields=("source_plan_id", "name"),
                    verification_method="read_copied_plan",
                ),
                ActionName.DELETE_PLAN: ActionDefinition(
                    name=ActionName.DELETE_PLAN,
                    description="删除投放计划",
                    scope="plan",
                    input_model=DeletePlanInput,
                    confirmation_fields=("target_id", "reason"),
                    verification_method="read_plan_absent",
                    destructive=True,
                ),
                ActionName.EDIT_PLAN: ActionDefinition(
                    name=ActionName.EDIT_PLAN,
                    description="编辑计划允许字段",
                    scope="plan",
                    input_model=EditPlanInput,
                    confirmation_fields=("target_id", "fields"),
                    verification_method="read_plan_fields",
                ),
                ActionName.UPDATE_PLAN_BID: ActionDefinition(
                    name=ActionName.UPDATE_PLAN_BID,
                    description="修改计划出价",
                    scope="plan",
                    input_model=UpdatePlanBidInput,
                    confirmation_fields=("target_id", "bid"),
                    verification_method="read_plan_bid",
                ),
                ActionName.UPDATE_TARGETING: ActionDefinition(
                    name=ActionName.UPDATE_TARGETING,
                    description="修改计划定向",
                    scope="plan",
                    input_model=UpdateTargetingInput,
                    confirmation_fields=("target_id", "targeting"),
                    verification_method="read_plan_targeting",
                ),
                ActionName.UPDATE_SCHEDULE: ActionDefinition(
                    name=ActionName.UPDATE_SCHEDULE,
                    description="修改计划投放时间",
                    scope="plan",
                    input_model=UpdateScheduleInput,
                    confirmation_fields=("target_id", "schedule"),
                    verification_method="read_plan_schedule",
                ),
                ActionName.BIND_EXISTING_MATERIAL: ActionDefinition(
                    name=ActionName.BIND_EXISTING_MATERIAL,
                    description="绑定已有素材",
                    scope="material",
                    input_model=BindExistingMaterialInput,
                    confirmation_fields=("target_id", "material_id"),
                    verification_method="read_material_bound",
                ),
                ActionName.UNBIND_EXISTING_MATERIAL: ActionDefinition(
                    name=ActionName.UNBIND_EXISTING_MATERIAL,
                    description="解绑已有素材",
                    scope="material",
                    input_model=UnbindExistingMaterialInput,
                    confirmation_fields=("target_id", "material_id"),
                    verification_method="read_material_unbound",
                    destructive=True,
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