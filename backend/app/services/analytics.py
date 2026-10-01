from pydantic import BaseModel

from app.execution.cdp.fixture_adapter import MetricSnapshot


class ComputedMetrics(BaseModel):
    roi: float | None
    gpm: float | None
    spend: float
    gmv: float
    orders: int
    online_viewers: int
    views: int = 0
    exposure_count: int | None = None
    view_count: int | None = None
    product_clicks: int | None = None
    view_conversion_rate: float | None = None
    exposure_view_rate: float | None = None


class AnalyticsService:
    def compute(self, snapshot: MetricSnapshot) -> ComputedMetrics:
        roi = (
            snapshot.roi
            if snapshot.roi is not None
            else (snapshot.gmv / snapshot.spend if snapshot.spend > 0 else None)
        )
        gpm = (
            snapshot.gpm
            if snapshot.gpm is not None
            else (snapshot.gmv / (snapshot.views / 1000) if snapshot.views > 0 else None)
        )
        return ComputedMetrics(
            roi=roi,
            gpm=gpm,
            spend=snapshot.spend,
            gmv=snapshot.gmv,
            orders=snapshot.orders,
            online_viewers=snapshot.online_viewers,
            views=snapshot.views,
            exposure_count=snapshot.exposure_count,
            view_count=snapshot.view_count,
            product_clicks=snapshot.product_clicks,
            view_conversion_rate=snapshot.view_conversion_rate,
            exposure_view_rate=snapshot.exposure_view_rate,
        )