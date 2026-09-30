from app.services.action_planner import ActionPlanner
from app.services.action_registry import ActionEnvelope, ActionName


def test_batch_preview_aborts_when_any_target_is_invalid(profile, plan_snapshot):
    actions = [
        ActionEnvelope(
            action_name=ActionName.PAUSE_PLAN,
            target_id="plan-1",
            params={},
        ),
        ActionEnvelope(
            action_name=ActionName.PAUSE_PLAN,
            target_id="missing-plan",
            params={},
        ),
    ]
    previews = ActionPlanner().preflight_batch(actions, profile, {"plan-1": plan_snapshot})
    assert all(not preview.allowed for preview in previews)


def test_batch_preview_limit_is_enforced(profile, plan_snapshot):
    actions = [
        ActionEnvelope(
            action_name=ActionName.PAUSE_PLAN,
            target_id="plan-1",
            params={},
        )
    ]
    try:
        ActionPlanner(max_batch_size=0).preflight_batch(actions, profile, {"plan-1": plan_snapshot})
    except ValueError as exc:
        assert "batch size" in str(exc)
    else:
        raise AssertionError("expected batch size validation")

def test_batch_preview_api_blocks_all(client, profile, plan_snapshot):
    client.app.state.plan_snapshot_provider = lambda target_id: plan_snapshot
    response = client.post(
        "/api/actions/batch-preview",
        json={
            "actions": [
                {"action_name": "pause_plan", "target_id": "plan-1", "params": {}},
                {"action_name": "pause_plan", "target_id": "missing-plan", "params": {}},
            ]
        },
    )
    assert response.status_code == 200
    assert all(not item["allowed"] for item in response.json())


def test_batch_confirmation_api_is_all_or_abort(client, profile, plan_snapshot):
    client.app.state.plan_snapshot_provider = lambda target_id: plan_snapshot
    response = client.post(
        "/api/actions/batch-confirmations",
        json={
            "actions": [
                {"action_name": "pause_plan", "target_id": "plan-1", "params": {}},
                {"action_name": "pause_plan", "target_id": "missing-plan", "params": {}},
            ]
        },
    )
    assert response.status_code == 409
