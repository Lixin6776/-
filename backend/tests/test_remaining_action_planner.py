from app.services.action_planner import ActionPlanner
from app.services.action_registry import ActionEnvelope, ActionName


def test_delete_requires_destructive_confirmation(profile, plan_snapshot):
    profile.allowed_actions = [*profile.allowed_actions, "delete_plan"]
    action = ActionEnvelope(
        action_name=ActionName.DELETE_PLAN,
        target_id="plan-1",
        params={"reason": "长期亏损"},
    )
    preview = ActionPlanner().preflight(action, profile, plan_snapshot)
    assert preview.allowed is True
    assert preview.destructive is True


def test_edit_rejects_non_allowlisted_field(profile, plan_snapshot):
    profile.allowed_actions = [*profile.allowed_actions, "edit_plan"]
    action = ActionEnvelope(
        action_name=ActionName.EDIT_PLAN,
        target_id="plan-1",
        params={"fields": {"unknown_field": "value"}},
    )
    preview = ActionPlanner().preflight(action, profile, plan_snapshot)
    assert preview.allowed is False
    assert "allowlist" in preview.blockers[0]