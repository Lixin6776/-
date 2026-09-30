import hashlib
import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ValidationError

from app.models import StrategyProfile
from app.services.action_registry import ActionEnvelope, ActionName, ActionRegistry


class PlanSnapshot(BaseModel):
    id: str
    name: str
    status: str
    budget: float


class ActionPreview(BaseModel):
    action_name: ActionName
    target_id: str
    target_name: str
    normalized_params: dict
    diff: dict
    blockers: list[str]
    warnings: list[str]
    allowed: bool
    strategy_profile_version: int
    expires_at: datetime
    preview_hash: str
    idempotency_key: str
    requires_confirmation: bool = True


class ActionPlanner:
    def __init__(self, ttl_minutes: int = 10) -> None:
        self.ttl_minutes = ttl_minutes
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
            blockers.append(f"策略画像不允许执行动作 {action.action_name.value}")

        normalized_params: dict = {}
        try:
            validated = definition.input_model.model_validate(
                {"target_id": action.target_id, **action.params}
            )
            normalized_params = validated.model_dump(mode="json")
        except ValidationError as exc:
            blockers.extend(f"参数错误：{error['msg']}" for error in exc.errors())

        if plan.id != action.target_id:
            blockers.append("目标计划与页面快照不一致")

        diff: dict = {}
        if action.action_name == ActionName.PAUSE_PLAN:
            if plan.status == "paused":
                blockers.append("计划已经是暂停状态")
            else:
                diff = {"status": {"before": plan.status, "after": "paused"}}
        elif action.action_name == ActionName.ENABLE_PLAN:
            if plan.status == "active":
                blockers.append("计划已经是启用状态")
            else:
                diff = {"status": {"before": plan.status, "after": "active"}}
        elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            target_budget = normalized_params.get("budget")
            daily_budget_max = profile.hard_constraints.get("daily_budget_max")
            if (
                target_budget is not None
                and daily_budget_max is not None
                and float(target_budget) > float(daily_budget_max)
            ):
                blockers.append(f"目标预算超过 daily_budget_max={daily_budget_max}")
            if target_budget is not None and target_budget == plan.budget:
                blockers.append("目标预算与当前预算相同")
            if target_budget is not None:
                diff = {"budget": {"before": plan.budget, "after": float(target_budget)}}

        normalized_action = {
            "action_name": action.action_name.value,
            "target_id": action.target_id,
            "params": normalized_params,
            "profile_version": profile.version,
            "before": plan.model_dump(mode="json"),
        }
        canonical = json.dumps(normalized_action, sort_keys=True, ensure_ascii=False)
        preview_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        idempotency_key = f"idem:{preview_hash}"

        return ActionPreview(
            action_name=action.action_name,
            target_id=action.target_id,
            target_name=plan.name,
            normalized_params=normalized_params,
            diff=diff,
            blockers=blockers,
            warnings=warnings,
            allowed=not blockers,
            strategy_profile_version=profile.version,
            expires_at=datetime.now(UTC) + timedelta(minutes=self.ttl_minutes),
            preview_hash=preview_hash,
            idempotency_key=idempotency_key,
        )