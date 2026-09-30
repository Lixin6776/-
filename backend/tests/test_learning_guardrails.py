from app.models import ExecutionJob, PendingConfirmation, StrategySuggestion
from app.services.learning import LearningService


def test_rejected_suggestion_is_remembered(db_session, profile):
    suggestion = StrategySuggestion(
        id="s1",
        strategy_profile_version=profile.version,
        suggestion_type="threshold_adjustment",
        proposed_change={"roi_floor_delta": 0.1},
        evidence={"sample_size": 24},
        confidence="high",
        status="proposed",
    )
    db_session.add(suggestion)
    db_session.commit()
    service = LearningService(db_session)
    service.reject(suggestion.id, reason="样本不足")
    assert service.was_rejected({"roi_floor_delta": 0.1}) is True


def test_replay_does_not_mutate_execution_history(db_session):
    confirmation = PendingConfirmation(
        id="c1",
        action_name="pause_plan",
        action_params={},
        preview_hash="hash",
        strategy_profile_version=1,
        idempotency_key="idem-1",
        expires_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        status="succeeded",
    )
    job = ExecutionJob(
        id="job-1",
        confirmation_id="c1",
        action_name="pause_plan",
        status="succeeded",
        result={"before": {"status": "active"}, "after": {"status": "paused"}},
    )
    db_session.add_all([confirmation, job])
    db_session.commit()
    before = dict(job.result)
    service = LearningService(db_session)
    service.replay(job.id)
    assert job.result == before