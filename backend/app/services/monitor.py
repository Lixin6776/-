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
    spend_delta: float | None = None
    minutes_since_previous: float | None = None
    live_ended: bool = False
    live_started_at: datetime | None = None
    review: dict | None = None


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
        review_notifier: Callable[[dict], None] | None = None,
        avg_online_provider: Callable[[], tuple[float | None, int]] | None = None,
        roi_target_provider: Callable[[], float | None] | None = None,
        baselines_provider: Callable[[], dict | None] | None = None,
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
        self._previous_captured_at: datetime | None = None
        self._previous_plan_status: str | None = None
        self.review_store = None
        self.review_notifier = review_notifier
        self.avg_online_provider = avg_online_provider
        # 复盘判「是否达标」要用计划里的实际 ROI 目标（和盯盘同一个来源），
        # 不能用策略里写死的值，否则同一场会出现两个目标。
        self.roi_target_provider = roi_target_provider
        # 判断阈值优先用「本账户历史分位」——给复盘报告算阈值用
        self.baselines_provider = baselines_provider
        self._latest_event: MonitorEvent | None = None

    def latest_event(self) -> MonitorEvent | None:
        return self._latest_event

    def build_event(self, reading: SnapshotReading) -> MonitorEvent:
        snapshot = reading.snapshot
        metrics = AnalyticsService().compute(snapshot)
        stale = snapshot.freshness != "fresh" or bool(reading.error)
        spend_delta = None
        minutes_since_previous = None
        if self._previous_metrics is not None:
            spend_delta = metrics.spend - self._previous_metrics.spend
            if self._previous_captured_at is not None:
                elapsed = snapshot.captured_at - self._previous_captured_at
                minutes_since_previous = max(0.0, elapsed.total_seconds() / 60)
        previous = self._previous_metrics or metrics
        signal = self.detector.evaluate(metrics, previous, stale=stale)
        if not stale:
            self._previous_metrics = metrics
            self._previous_captured_at = snapshot.captured_at
        profile = self._profile_provider()
        reason = signal.reason
        if reading.error:
            reason = f"CDP 读取失败，已暂停判断：{reading.error}"
        live_ended = snapshot.plan_status == "ended"
        review = None
        if live_ended and self.review_store is not None:
            from app.services.live_review import build_live_review

            avg_online = None
            samples = 0
            if self.avg_online_provider is not None:
                try:
                    avg_online, samples = self.avg_online_provider()
                except Exception:  # noqa: BLE001
                    avg_online, samples = None, 0
            plan_target = None
            if self.roi_target_provider is not None:
                try:
                    plan_target = self.roi_target_provider()
                except Exception:  # noqa: BLE001
                    plan_target = None
            baselines = None
            if self.baselines_provider is not None:
                try:
                    baselines = self.baselines_provider()
                except Exception:  # noqa: BLE001
                    baselines = None
            review = self.review_store.add_if_absent(
                build_live_review(
                    snapshot,
                    metrics,
                    profile,
                    snapshot.captured_at,
                    avg_online=avg_online,
                    online_samples=samples,
                    roi_target=plan_target,
                    baselines=baselines,
                )
            )
            if self.review_notifier is not None:
                self.review_notifier(review)
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
            spend_delta=spend_delta,
            minutes_since_previous=minutes_since_previous,
            live_ended=live_ended,
            live_started_at=snapshot.live_started_at,
            review=review,
        )
        self._previous_plan_status = snapshot.plan_status
        self._latest_event = event
        return event


class MonitorService(_MonitorCore):
    def __init__(
        self,
        fixture_path: Path,
        profile_version: int = 1,
        interval_seconds: int = 300,
        profile_provider: Callable[[], MonitorProfile] | None = None,
        review_store=None,
        review_notifier: Callable[[dict], None] | None = None,
        avg_online_provider: Callable[[], tuple[float | None, int]] | None = None,
        roi_target_provider: Callable[[], float | None] | None = None,
        baselines_provider: Callable[[], dict | None] | None = None,
    ) -> None:
        super().__init__(
            profile_version=profile_version,
            profile_provider=profile_provider,
            review_notifier=review_notifier,
            avg_online_provider=avg_online_provider,
            # 之前漏传了 roi_target_provider —— 复盘"用计划目标"那条一直没生效
            roi_target_provider=roi_target_provider,
            baselines_provider=baselines_provider,
        )
        self.fixture_path = fixture_path
        self.review_store = review_store
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
        review_store=None,
        review_notifier: Callable[[dict], None] | None = None,
        avg_online_provider: Callable[[], tuple[float | None, int]] | None = None,
        roi_target_provider: Callable[[], float | None] | None = None,
        baselines_provider: Callable[[], dict | None] | None = None,
    ) -> None:
        super().__init__(
            profile_version=profile_version,
            profile_provider=profile_provider,
            review_notifier=review_notifier,
            avg_online_provider=avg_online_provider,
            # 之前漏传了 roi_target_provider —— 复盘"用计划目标"那条一直没生效
            roi_target_provider=roi_target_provider,
            baselines_provider=baselines_provider,
        )
        self.snapshot_provider = snapshot_provider
        self.review_store = review_store
        self.interval_seconds = interval_seconds

    async def tick(self) -> MonitorEvent:
        reading = await self.snapshot_provider()
        return self.build_event(reading)
