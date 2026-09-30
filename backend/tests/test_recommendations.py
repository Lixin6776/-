from app.services.changes import ChangeLevel, ChangeSignal
from app.services.recommendations import RecommendationEngine


def test_action_change_creates_recommendation(profile):
    signal = ChangeSignal(
        level=ChangeLevel.ACTION,
        reason="ROI 显著下降",
        roi_change=-0.25,
        spend_change=0.30,
    )
    recommendation = RecommendationEngine().recommend(signal, profile)
    assert recommendation is not None
    assert recommendation.action == "update_plan_budget"
    assert "人工确认" in recommendation.reason