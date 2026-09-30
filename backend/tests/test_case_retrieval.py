import pytest

from app.models import LearningCase
from app.services.case_library import CaseLibrary, CaseQuery


@pytest.fixture
def case_library(db_session):
    cases = [
        LearningCase(
            id="match",
            strategy_profile_version=1,
            action_name="pause_plan",
            context={
                "business_direction": "稳定放量",
                "primary_objective": "提升成交额",
                "plan_stage": "mature",
                "hour": 20,
                "spend": 480,
                "roi": 2.4,
            },
            status="observed",
        ),
        LearningCase(
            id="other",
            strategy_profile_version=1,
            action_name="update_plan_budget",
            context={
                "business_direction": "保利润",
                "primary_objective": "控制成本",
                "plan_stage": "cold",
                "hour": 10,
                "spend": 100,
                "roi": 1.0,
            },
            status="observed",
        ),
    ]
    db_session.add_all(cases)
    db_session.commit()
    return CaseLibrary(db_session)


@pytest.fixture
def query():
    return CaseQuery(
        business_direction="稳定放量",
        primary_objective="提升成交额",
        action_name="pause_plan",
        plan_stage="mature",
        hour=20,
        spend=500,
        roi=2.5,
    )


def test_similar_cases_rank_same_direction_and_action_first(case_library, query):
    matches = case_library.find_similar(query, limit=3)
    assert matches[0].case.context["business_direction"] == query.business_direction
    assert matches[0].case.action_name == query.action_name