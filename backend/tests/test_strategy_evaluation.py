import pytest

from app.models import DecisionOutcome, LearningCase
from app.services.evaluation import StrategyEvaluationService


@pytest.fixture
def low_sample_cases(db_session):
    cases = []
    for index in range(3):
        case = LearningCase(
            id=f"case-{index}",
            strategy_profile_version=1,
            action_name="pause_plan",
            context={},
            status="observed",
        )
        outcome = DecisionOutcome(
            id=f"outcome-{index}",
            case_id=case.id,
            metric_window="30m",
            metrics={"roi_delta": 0.2},
        )
        db_session.add_all([case, outcome])
        cases.append(case)
    db_session.commit()
    return cases


def test_small_sample_never_has_high_confidence(db_session, low_sample_cases):
    service = StrategyEvaluationService(db_session)
    evaluation = service.evaluate([case.id for case in low_sample_cases])
    assert evaluation.sample_size < 5
    assert evaluation.confidence == "low"
    assert evaluation.verdict == "insufficient_data"