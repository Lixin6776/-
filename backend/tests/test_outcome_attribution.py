import pytest

from app.models import LearningCase
from app.services.outcomes import OutcomeAttributionService


@pytest.fixture
def case(db_session):
    item = LearningCase(
        id="case-1",
        strategy_profile_version=1,
        action_name="pause_plan",
        context={},
        status="observed",
    )
    db_session.add(item)
    db_session.commit()
    return item


@pytest.fixture
def outcome_service(db_session):
    return OutcomeAttributionService(db_session)


def test_outcomes_include_short_and_long_windows(outcome_service, case):
    outcomes = outcome_service.record(
        case_id=case.id,
        before={"roi": 2.0, "spend": 400},
        after={"roi": 2.6, "spend": 450},
        windows=["5m", "30m"],
    )
    assert [outcome.metric_window for outcome in outcomes] == ["5m", "30m"]
    assert outcomes[0].metrics["roi_delta"] == 0.6