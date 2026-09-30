
from app.services.action_planner import PlanSnapshot
from app.services.confirmations import ConfirmationService


def test_preview_endpoint_uses_current_plan_snapshot(client, profile):
    client.app.state.plan_snapshot_provider = lambda target_id: PlanSnapshot(
        id=target_id,
        name="计划 A",
        status="active",
        budget=1000,
    )
    response = client.post(
        "/api/actions/preview",
        json={
            "action": {
                "action_name": "pause_plan",
                "target_id": "plan-1",
                "params": {},
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is True
    assert response.json()["diff"]["status"]["after"] == "paused"


def test_execute_endpoint_creates_pending_job(client, db_session, preview):
    confirmation = ConfirmationService(db_session).create_from_preview(preview)
    response = client.post(f"/api/actions/confirmations/{confirmation.id}/execute")
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    jobs = client.get("/api/actions/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["confirmation_id"] == confirmation.id