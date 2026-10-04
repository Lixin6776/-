import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class MetricSnapshot(BaseModel):
    captured_at: datetime
    live_started_at: datetime | None = None
    freshness: str
    plan_status: str
    plan_budget: float
    spend: float
    gmv: float
    orders: int
    views: int
    online_viewers: int
    roi: float | None = None
    gpm: float | None = None
    exposure_count: int | None = None
    view_count: int | None = None
    product_clicks: int | None = None
    view_conversion_rate: float | None = None
    exposure_view_rate: float | None = None


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