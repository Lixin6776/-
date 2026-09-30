import hashlib
import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ValidationError

from app.models import StrategyProfile
from app.services.action_registry import ActionEnvelope, ActionName, ActionRegistry

EDIT_FIELD_ALLOWLIST = {"name", "budget", "bid", "targeting", "schedule"}
TARGET_MUST_MATCH = {
    ActionName.PAUSE_PLAN,
    ActionName.ENABLE_PLAN,
    ActionName.UPDATE_PLAN_BUDGET,
    ActionName.COPY_PLAN,
    ActionName.DELETE_PLAN,
    ActionName.EDIT_PLAN,
    ActionName.UPDATE_PLAN_BID,
    ActionName.UPDATE_TARGETING,
    ActionName.UPDATE_SCHEDULE,
    ActionName.BIND_EXISTING_MATERIAL,
    ActionName.UNBIND_EXISTING_MATERIAL,
}


class PlanSnapshot(BaseModel):
    id: str
    name: str
    status: str
    budget: float
    bid: float | None = None
    roi_goal: float | None = None
    roi: float | None = None
    spend: float | None = None
    gmv: float | None = None
    orders: int | None = None
    targeting: dict = {}
    schedule: dict = {}
    materials: list[str] = []
    available_materials: list[str] = []


class ActionPreview(BaseModel):
    action_name: ActionName
    target_id: str
    target_name: str
    normalized_params: dict
    diff: dict
    blockers: list[str]
    warnings: list[str]
    allowed: bool
    destructive: bool = False
    strategy_profile_version: int
    expires_at: datetime
    preview_hash: str
    idempotency_key: str
    requires_confirmation: bool = True


class ActionPlanner:
    def __init__(self, ttl_minutes: int = 10, max_batch_size: int = 20) -> None:
        self.ttl_minutes = ttl_minutes
        self.max_batch_size = max_batch_size
        self.registry = ActionRegistry.default()

    def preflight(
        self,
        action: ActionEnvelope,
        profile: StrategyProfile,
        plan: PlanSnapshot,
    ) -> ActionPreview:
        definition = self.registry.get(action.action_name)
        blockers: list[str] = []
        warnings: list[str] = []

        if action.action_name.value not in profile.allowed_actions:
            blockers.append(f"投放策略不允许执行动作 {action.action_name.value}")

        normalized_params: dict = {}
        try:
            validated = definition.input_model.model_validate(
                {"target_id": action.target_id, **action.params}
            )
            normalized_params = validated.model_dump(mode="json")
        except ValidationError as exc:
            blockers.extend(f"参数错误：{error['msg']}" for error in exc.errors())

        if action.action_name in TARGET_MUST_MATCH and plan.id != action.target_id:
            blockers.append("目标计划与页面快照不一致")

        diff = self._build_diff(action, normalized_params, blockers, plan, profile)
        normalized_action = {
            "action_name": action.action_name.value,
            "target_id": action.target_id,
            "params": normalized_params,
            "profile_version": profile.version,
            "before": plan.model_dump(mode="json"),
        }
        canonical = json.dumps(normalized_action, sort_keys=True, ensure_ascii=False)
        preview_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return ActionPreview(
            action_name=action.action_name,
            target_id=action.target_id,
            target_name=plan.name,
            normalized_params=normalized_params,
            diff=diff,
            blockers=blockers,
            warnings=warnings,
            allowed=not blockers,
            destructive=definition.destructive,
            strategy_profile_version=profile.version,
            expires_at=datetime.now(UTC) + timedelta(minutes=self.ttl_minutes),
            preview_hash=preview_hash,
            idempotency_key=f"idem:{preview_hash}",
        )

    def _build_diff(
        self,
        action: ActionEnvelope,
        params: dict,
        blockers: list[str],
        plan: PlanSnapshot,
        profile: StrategyProfile,
    ) -> dict:
        if action.action_name == ActionName.PAUSE_PLAN:
            if plan.status == "paused":
                blockers.append("计划已经是暂停状态")
            return {"status": {"before": plan.status, "after": "paused"}}
        if action.action_name == ActionName.ENABLE_PLAN:
            if plan.status == "active":
                blockers.append("计划已经是启用状态")
            return {"status": {"before": plan.status, "after": "active"}}
        if action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            return self._budget_diff(float(params["budget"]), blockers, plan, profile)
        if action.action_name == ActionName.CREATE_PLAN:
            return self._budget_diff(float(params["budget"]), blockers, plan, profile) | {
                "name": {"before": None, "after": params["name"]},
                "roi_goal": {"before": None, "after": params["roi_goal"]},
            }
        if action.action_name == ActionName.COPY_PLAN:
            if params.get("source_plan_id") not in {None, plan.id}:
                blockers.append("复制来源计划不存在")
            return {"name": {"before": plan.name, "after": params["name"]}}
        if action.action_name == ActionName.DELETE_PLAN:
            return {"plan": {"before": plan.id, "after": None}}
        if action.action_name == ActionName.EDIT_PLAN:
            fields = params.get("fields", {})
            invalid = set(fields) - EDIT_FIELD_ALLOWLIST
            if invalid:
                blockers.append(f"编辑字段不在 allowlist 中：{sorted(invalid)}")
            return {key: {"before": getattr(plan, key, None), "after": value} for key, value in fields.items()}
        if action.action_name == ActionName.UPDATE_PLAN_BID:
            return {"bid": {"before": plan.bid, "after": float(params["bid"])}}
        if action.action_name == ActionName.UPDATE_TARGETING:
            return {"targeting": {"before": plan.targeting, "after": params["targeting"]}}
        if action.action_name == ActionName.UPDATE_SCHEDULE:
            return {"schedule": {"before": plan.schedule, "after": params["schedule"]}}
        if action.action_name == ActionName.BIND_EXISTING_MATERIAL:
            material_id = params["material_id"]
            if material_id not in plan.available_materials:
                blockers.append("素材不在账户可用素材库中")
            if material_id in plan.materials:
                blockers.append("素材已经绑定")
            return {"materials": {"before": list(plan.materials), "after": [*plan.materials, material_id]}}
        if action.action_name == ActionName.UNBIND_EXISTING_MATERIAL:
            material_id = params["material_id"]
            if material_id not in plan.materials:
                blockers.append("素材当前未绑定")
            return {"materials": {"before": list(plan.materials), "after": [item for item in plan.materials if item != material_id]}}
        return {}

    @staticmethod
    def _budget_diff(
        target_budget: float,
        blockers: list[str],
        plan: PlanSnapshot,
        profile: StrategyProfile,
    ) -> dict:
        daily_budget_max = profile.hard_constraints.get("daily_budget_max")
        if daily_budget_max is not None and target_budget > float(daily_budget_max):
            blockers.append(f"目标预算超过 daily_budget_max={daily_budget_max}")
        if target_budget == plan.budget:
            blockers.append("目标预算与当前预算相同")
        return {"budget": {"before": plan.budget, "after": target_budget}}
    def preflight_batch(
        self,
        actions: list[ActionEnvelope],
        profile: StrategyProfile,
        plans: dict[str, PlanSnapshot],
    ) -> list[ActionPreview]:
        if len(actions) > self.max_batch_size:
            raise ValueError(f"batch size exceeds limit {self.max_batch_size}")
        previews: list[ActionPreview] = []
        for action in actions:
            plan = plans.get(action.target_id)
            if plan is None or plan.status == "missing":
                plan = plan or PlanSnapshot(
                    id=action.target_id,
                    name="未知计划",
                    status="missing",
                    budget=0,
                )
                preview = self.preflight(action, profile, plan)
                preview = preview.model_copy(
                    update={
                        "blockers": [*preview.blockers, "批量预检目标不存在"],
                        "allowed": False,
                    }
                )
            else:
                preview = self.preflight(action, profile, plan)
            previews.append(preview)
        if any(not preview.allowed for preview in previews):
            previews = [
                preview.model_copy(
                    update={
                        "blockers": [
                            *preview.blockers,
                            "批量操作已全部中止：存在无效目标",
                        ],
                        "allowed": False,
                    }
                )
                for preview in previews
            ]
        return previews
