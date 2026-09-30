from app.services.action_planner import PlanSnapshot


def test_current_plan_endpoint_returns_read_only_snapshot(client, monkeypatch):
    from app.api import plans

    snapshot = PlanSnapshot(
        id="plan-1",
        name="计划 plan-1",
        status="active",
        budget=1000,
        roi_goal=2.6,
    )
    monkeypatch.setattr(
        plans.CdpPlanReader,
        "read_current",
        lambda self: snapshot,
    )

    response = client.get("/api/plans/current")

    assert response.status_code == 200
    assert response.json()["id"] == "plan-1"
    assert response.json()["budget"] == 1000
    assert response.json()["roi_goal"] == 2.6
