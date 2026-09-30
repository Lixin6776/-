import pytest

from app.models import StrategyEvaluation
from app.services.suggestions import SuggestionEngine


@pytest.fixture
def low_confidence_evaluation():
    return StrategyEvaluation(
        id="eval-low",
        sample_size=3,
        effect_size=0.2,
        confidence="low",
        verdict="insufficient_data",
        evidence={"counterexamples": 1},
    )


@pytest.fixture
def strong_evaluation():
    return StrategyEvaluation(
        id="eval-strong",
        sample_size=24,
        effect_size=0.4,
        confidence="high",
        verdict="beneficial",
        evidence={"counterexamples": 3, "case_ids": ["a", "b"]},
    )


def test_low_confidence_does_not_create_suggestion(low_confidence_evaluation, profile):
    suggestion = SuggestionEngine().propose(low_confidence_evaluation, [], profile)
    assert suggestion is None


def test_strong_evidence_creates_proposed_change(strong_evaluation, profile):
    suggestion = SuggestionEngine().propose(strong_evaluation, [], profile)
    assert suggestion is not None
    assert suggestion.status == "proposed"
    assert suggestion.proposed_change
    assert suggestion.evidence["sample_size"] >= 20