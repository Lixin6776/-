import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import DecisionOutcome


class OutcomeAttributionService:
    DELTA_KEYS = ("roi", "spend", "gmv", "orders", "gpm", "online_viewers", "budget")

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        case_id: str,
        before: dict,
        after: dict,
        windows: list[str],
    ) -> list[DecisionOutcome]:
        metrics = {
            f"{key}_delta": round(float(after.get(key, 0)) - float(before.get(key, 0)), 10)
            for key in self.DELTA_KEYS
        }
        outcomes = [
            DecisionOutcome(
                id=str(uuid.uuid4()),
                case_id=case_id,
                metric_window=window,
                metrics={**metrics, "before": before, "after": after},
                observed_at=datetime.now(UTC),
            )
            for window in windows
        ]
        self.session.add_all(outcomes)
        self.session.commit()
        return outcomes