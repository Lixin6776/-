import pytest

from app.services.action_planner import ActionPlanner, PlanSnapshot
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.fixture
def plan_snapshot():
    return PlanSnapshot(id="plan-1", name="计划 A", status="active", budget=1000)


def test_budget_above_profile_limit_is_blocked(profile, plan_snapshot):
    action = ActionEnvelope(
        action_name=ActionName.UPDATE_PLAN_BUDGET,
        target_id="plan-1",
        params={"budget": 6000},
    )
    preview = ActionPlanner().preflight(action, profile, plan_snapshot)
    assert preview.allowed is False
    assert "daily_budget_max" in preview.blockers[0]


def test_pause_preview_contains_required_confirmation_fields(profile, plan_snapshot):
    action = ActionEnvelope(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        params={},
    )
    preview = ActionPlanner().preflight(action, profile, plan_snapshot)
    assert preview.allowed is True
    assert preview.diff["status"]["before"] == "active"
    assert preview.diff["status"]["after"] == "paused"
    assert preview.strategy_profile_version == profile.version
    assert preview.idempotency_key