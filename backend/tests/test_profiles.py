def test_profile_versions_are_immutable(client):
    payload = {
        "name": "稳定放量",
        "business_direction": "稳定放量",
        "primary_objective": "ROI >= 2.5 且提升成交额",
        "secondary_objectives": ["保持在线人数"],
        "hard_constraints": {"daily_budget_max": 5000},
        "monitoring_config": {"interval_minutes": 5},
        "allowed_actions": ["pause_plan", "update_plan_budget"],
        "notification_policy": {"dedupe_minutes": 10},
    }
    first = client.post("/api/profiles/versions", json=payload)
    assert first.status_code == 201
    assert first.json()["version"] == 1

    payload["hard_constraints"] = {"daily_budget_max": 4500}
    second = client.post("/api/profiles/versions", json=payload)
    assert second.status_code == 201
    assert second.json()["version"] == 2

    active = client.get("/api/profiles/active").json()
    assert active["version"] == 2
    assert active["hard_constraints"]["daily_budget_max"] == 4500