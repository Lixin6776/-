from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.execution.cdp.fixture_adapter import FixturePageAdapter, MetricSnapshot
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
    metrics: ComputedMetrics
    plan_status: str
    plan_budget: float
    source: str


@dataclass(frozen=True)
class SnapshotReading:
    snapshot: MetricSnapshot
    source: str
    error: str = ""


class _MonitorCore:
    def __init__(
        self,
        profile_version: int = 1,
        profile_provider: Callable[[], MonitorProfile] | None = None,
    ) -> None:
        self._default_profile = MonitorProfile(
            version=profile_version,
            business_direction="稳定放量",
            primary_objective="ROI >= 2.5",
            hard_constraints={},
        )
        self._profile_provider = profile_provider or (lambda: self._default_profile)
        self.detector = ChangeDetector()
        self._previous_metrics: ComputedMetrics | None = None
        self._latest_event: MonitorEvent | None = None

    def latest_event(self) -> MonitorEvent | None:
        return self._latest_event

    def build_event(self, reading: SnapshotReading) -> MonitorEvent:
        snapshot = reading.snapshot
        metrics = AnalyticsService().compute(snapshot)
        stale = snapshot.freshness != "fresh" or bool(reading.error)
        previous = self._previous_metrics or metrics
        signal = self.detector.evaluate(metrics, previous, stale=stale)
        if not stale:
            self._previous_metrics = metrics
        profile = self._profile_provider()
        reason = signal.reason
        if reading.error:
            reason = f"CDP 读取失败，已暂停判断：{reading.error}"
        event = MonitorEvent(
            captured_at=snapshot.captured_at,
            freshness=snapshot.freshness,
            banner=(
                f"当前投放策略 v{profile.version}；大方向={profile.business_direction}；"
                f"目标={profile.primary_objective}；约束={profile.hard_constraints}"
            ),
            level=signal.level,
            reason=reason,
            profile_version=profile.version,
            metrics=metrics,
            plan_status=snapshot.plan_status,
            plan_budget=snapshot.plan_budget,
            source=reading.source,
        )
        self._latest_event = event
        return event


class MonitorService(_MonitorCore):
    def __init__(
        self,
        fixture_path: Path,
        profile_version: int = 1,
        interval_seconds: int = 300,
        profile_provider: Callable[[], MonitorProfile] | None = None,
    ) -> None:
        super().__init__(
            profile_version=profile_version,
            profile_provider=profile_provider,
        )
        self.fixture_path = fixture_path
        self.interval_seconds = interval_seconds

    def tick(self) -> MonitorEvent:
        snapshot = FixturePageAdapter().read_snapshot(self.fixture_path)
        return self.build_event(SnapshotReading(snapshot=snapshot, source="fixture"))


class AsyncMonitorService(_MonitorCore):
    def __init__(
        self,
        snapshot_provider: Callable[[], Awaitable[SnapshotReading]],
        profile_version: int = 1,
        interval_seconds: int = 300,
        profile_provider: Callable[[], MonitorProfile] | None = None,
    ) -> None:
        super().__init__(
            profile_version=profile_version,
            profile_provider=profile_provider,
        )
        self.snapshot_provider = snapshot_provider
        self.interval_seconds = interval_seconds

    async def tick(self) -> MonitorEvent:
        reading = await self.snapshot_provider()
        return self.build_event(reading)
