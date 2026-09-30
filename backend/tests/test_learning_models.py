from app.models import LearningCase


def test_learning_case_links_execution_history(db_session):
    case = LearningCase(
        id="case-1",
        strategy_profile_version=3,
        recommendation_id="rec-1",
        confirmation_id="conf-1",
        execution_job_id="job-1",
        action_name="pause_plan",
        context={"roi": 1.8, "spend": 500},
        status="observed",
    )
    db_session.add(case)
    db_session.commit()
    assert db_session.get(LearningCase, "case-1").strategy_profile_version == 3