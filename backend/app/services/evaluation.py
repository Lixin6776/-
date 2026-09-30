import statistics
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DecisionOutcome, StrategyEvaluation


class StrategyEvaluationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(self, case_ids: list[str]) -> StrategyEvaluation:
        outcomes = list(
            self.session.scalars(
                select(DecisionOutcome).where(DecisionOutcome.case_id.in_(case_ids))
            )
        )
        deltas = [float(outcome.metrics.get("roi_delta", 0)) for outcome in outcomes]
        sample_size = len(deltas)
        mean_delta = statistics.mean(deltas) if deltas else 0
        median_delta = statistics.median(deltas) if deltas else 0
        variance = statistics.pvariance(deltas) if len(deltas) > 1 else 0
        counterexamples = sum(1 for value in deltas if value < 0)
        success_rate = sum(1 for value in deltas if value > 0) / sample_size if sample_size else 0

        if sample_size < 5:
            confidence = "low"
            verdict = "insufficient_data"
        else:
            confidence = "medium" if sample_size < 20 else "high"
            if mean_delta > 0.05:
                verdict = "beneficial"
            elif mean_delta < -0.05:
                verdict = "harmful"
            else:
                verdict = "neutral"

        evaluation = StrategyEvaluation(
            id=str(uuid.uuid4()),
            case_id=case_ids[0] if case_ids else None,
            sample_size=sample_size,
            effect_size=round(mean_delta, 10),
            confidence=confidence,
            verdict=verdict,
            evidence={
                "mean_roi_delta": round(mean_delta, 10),
                "median_roi_delta": round(median_delta, 10),
                "variance": round(variance, 10),
                "success_rate": round(success_rate, 10),
                "counterexamples": counterexamples,
                "case_ids": case_ids,
            },
            created_at=datetime.now(UTC),
        )
        self.session.add(evaluation)
        self.session.commit()
        self.session.refresh(evaluation)
        return evaluation