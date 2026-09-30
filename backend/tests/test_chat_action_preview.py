from app.services.action_planner import PlanSnapshot


def test_chat_can_return_structured_action_preview(client, profile):
    client.app.state.plan_snapshot_provider = lambda target_id: PlanSnapshot(
        id=target_id,
        name="计划 A",
        status="active",
        budget=1000,
    )
    payload = {
        "message": "把计划 plan-1 的预算改成 800",
        "proposed_action": {
            "action_name": "update_plan_budget",
            "target_id": "plan-1",
            "params": {"budget": 800},
        },
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "recommendation"
    assert body["preview"]["allowed"] is True
    assert body["preview"]["requires_confirmation"] is True