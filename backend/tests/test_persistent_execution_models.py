from datetime import UTC, datetime, timedelta

from app.models import ExecutionJob, ExecutionLog, PendingConfirmation


def test_confirmation_and_job_persist(db_session):
    confirmation = PendingConfirmation(
        id="c1",
        recommendation_id="r1",
        action_name="pause_plan",
        action_params={"target_id": "plan-1"},
        preview_hash="hash",
        strategy_profile_version=1,
        idempotency_key="idem-1",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    job = ExecutionJob(id="j1", confirmation_id="c1", action_name="pause_plan")
    log = ExecutionLog(id="l1", job_id="j1", phase="preflight", payload={"allowed": True})
    db_session.add_all([confirmation, job, log])
    db_session.commit()
    assert db_session.get(PendingConfirmation, "c1").status == "pending"
    assert db_session.get(ExecutionJob, "j1").status == "pending"
    assert db_session.get(ExecutionLog, "l1").phase == "preflight"