from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from app.execution.cdp.fixture_adapter import FixturePageAdapter
from app.services.analytics import AnalyticsService, ComputedMetrics
from app.services.changes import ChangeDetector


class MonitorProfile(BaseModel):
    version: int
    business_direction: str
    primary_objective: str
    hard_constraints: dict


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
        profile_provider: Callable[[], MonitorProfile] | None = None,
    ) -> None:
        self.fixture_path = fixture_path
        self.interval_seconds = interval_seconds
        self._default_profile = MonitorProfile(
            version=profile_version,
            business_direction="稳定放量",
            primary_objective="ROI >= 2.5",
            hard_constraints={},
        )
        self._profile_provider = profile_provider or (lambda: self._default_profile)
        self.detector = ChangeDetector()
        self._previous_metrics: ComputedMetrics | None = None

    def tick(self) -> MonitorEvent:
        snapshot = FixturePageAdapter().read_snapshot(self.fixture_path)
        metrics = AnalyticsService().compute(snapshot)
        stale = snapshot.freshness != "fresh"
        previous = self._previous_metrics or metrics
        signal = self.detector.evaluate(metrics, previous, stale=stale)
        if not stale:
            self._previous_metrics = metrics
        profile = self._profile_provider()
        return MonitorEvent(
            captured_at=datetime.now(UTC),
            freshness=snapshot.freshness,
            banner=(
                f"当前策略画像 v{profile.version}；大方向={profile.business_direction}；"
                f"目标={profile.primary_objective}；约束={profile.hard_constraints}"
            ),
            level=signal.level,
            reason=signal.reason,
            profile_version=profile.version,
        )