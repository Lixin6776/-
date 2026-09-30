from pydantic import BaseModel

from app.execution.cdp.fixture_adapter import MetricSnapshot


class ComputedMetrics(BaseModel):
    roi: float | None
    gpm: float | None
    spend: float
    gmv: float
    orders: int
    online_viewers: int


class AnalyticsService:
    def compute(self, snapshot: MetricSnapshot) -> ComputedMetrics:
        roi = snapshot.gmv / snapshot.spend if snapshot.spend > 0 else None
        gpm = snapshot.gmv / (snapshot.views / 1000) if snapshot.views > 0 else None
        return ComputedMetrics(
            roi=roi,
            gpm=gpm,
            spend=snapshot.spend,
            gmv=snapshot.gmv,
            orders=snapshot.orders,
            online_viewers=snapshot.online_viewers,
        )