import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class MetricSnapshot(BaseModel):
    captured_at: datetime
    freshness: str
    plan_status: str
    plan_budget: float
    spend: float
    gmv: float
    orders: int
    views: int
    online_viewers: int


class FixturePageAdapter:
    def read_snapshot(self, path: Path) -> MetricSnapshot:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return MetricSnapshot(
                captured_at=raw["captured_at"],
                freshness=raw["freshness"],
                plan_status=raw["plan"]["status"],
                plan_budget=raw["plan"]["budget"],
                **raw["metrics"],
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("Malformed page snapshot") from exc