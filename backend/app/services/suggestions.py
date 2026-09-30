import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import StrategyEvaluation, StrategyProfile, StrategySuggestion


class SuggestionEngine:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def propose(
        self,
        evaluation: StrategyEvaluation,
        matches: list,
        profile: StrategyProfile,
    ) -> StrategySuggestion | None:
        if evaluation.confidence == "low" or evaluation.sample_size < 20:
            return None
        if evaluation.verdict not in {"beneficial", "harmful"}:
            return None
        effect = float(evaluation.effect_size or 0)
        if evaluation.verdict == "beneficial":
            suggestion_type = "threshold_adjustment"
            proposed_change = {
                "primary_objective": profile.primary_objective,
                "roi_floor_delta": round(max(effect * 0.25, 0.05), 2),
            }
        else:
            suggestion_type = "action_priority"
            proposed_change = {
                "primary_objective": profile.primary_objective,
                "de_prioritize_action": "pause_plan",
            }
        suggestion = StrategySuggestion(
            id=str(uuid.uuid4()),
            strategy_profile_version=profile.version,
            suggestion_type=suggestion_type,
            proposed_change=proposed_change,
            evidence={
                "sample_size": evaluation.sample_size,
                "effect_size": evaluation.effect_size,
                "confidence": evaluation.confidence,
                "counterexamples": evaluation.evidence.get("counterexamples", 0),
                "similar_cases": len(matches),
            },
            confidence=evaluation.confidence,
            status="proposed",
            created_at=datetime.now(UTC),
        )
        if self.session is not None:
            self.session.add(suggestion)
            self.session.commit()
            self.session.refresh(suggestion)
        return suggestion