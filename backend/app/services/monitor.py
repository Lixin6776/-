from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from app.execution.cdp.fixture_adapter import FixturePageAdapter
from app.services.analytics import AnalyticsService
from app.services.changes import ChangeDetector


class MonitorEvent(BaseModel):
    captured_at: datetime
    freshness: str
    banner: str
    level: str
    reason: str
    profile_version: int


class MonitorService:
    def __init__(
        self,
        fixture_path: Path,
        profile_version: int = 1,
        interval_seconds: int = 300,
    ) -> None:
        self.fixture_path = fixture_path
        self.profile_version = profile_version
        self.interval_seconds = interval_seconds
        self.detector = ChangeDetector()

    def tick(self) -> MonitorEvent:
        snapshot = FixturePageAdapter().read_snapshot(self.fixture_path)
        metrics = AnalyticsService().compute(snapshot)
        signal = self.detector.evaluate(metrics, metrics, stale=snapshot.freshness != "fresh")
        return MonitorEvent(
            captured_at=datetime.now(timezone.utc),
            freshness=snapshot.freshness,
            banner=f"当前策略画像 v{self.profile_version}；大方向=稳定放量；ROI >= 2.5",
            level=signal.level,
            reason=signal.reason,
            profile_version=self.profile_version,
        )