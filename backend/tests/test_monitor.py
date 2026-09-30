import json
from pathlib import Path

import pytest

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.services.monitor import (
    AsyncMonitorService,
    MonitorProfile,
    MonitorService,
    SnapshotReading,
)


@pytest.fixture
def monitor_service():
    return MonitorService(Path("tests/fixtures/plan_live_snapshot.json"), profile_version=1)


def _write_snapshot(path: Path, *, spend: float, gmv: float) -> None:
    path.write_text(
        json.dumps(
            {
                "captured_at": "2026-09-30T20:15:00+08:00",
                "freshness": "fresh",
                "plan": {"status": "active", "budget": 1200},
                "metrics": {
                    "spend": spend,
                    "gmv": gmv,
                    "orders": 20,
                    "views": 1000,
                    "online_viewers": 120,
                },
            }
        ),
        encoding="utf-8",
    )


def test_monitor_emits_profile_and_freshness(monitor_service):
    event = monitor_service.tick()
    assert event.profile_version >= 1
    assert event.freshness in {"fresh", "stale"}
    assert "投放策略" in event.banner


def test_monitor_detects_change_across_windows(tmp_path):
    path = tmp_path / "snapshot.json"
    service = MonitorService(path)
    _write_snapshot(path, spend=300, gmv=900)
    assert service.tick().level == "normal"
    _write_snapshot(path, spend=400, gmv=960)
    assert service.tick().level == "watch"
    _write_snapshot(path, spend=500, gmv=950)
    assert service.tick().level == "action"


def test_monitor_uses_current_profile_snapshot(monitor_service):
    profile = MonitorProfile(
        version=2,
        business_direction="保利润",
        primary_objective="ROI >= 3.0",
        hard_constraints={"daily_budget_max": 3000},
    )
    service = MonitorService(
        Path("tests/fixtures/plan_live_snapshot.json"),
        profile_provider=lambda: profile,
    )
    event = service.tick()
    assert event.profile_version == 2
    assert "保利润" in event.banner
    assert "ROI >= 3.0" in event.banner
    assert "daily_budget_max" in event.banner


@pytest.mark.asyncio
async def test_async_monitor_emits_cdp_metrics_and_source():
    snapshot = MetricSnapshot(
        captured_at="2026-09-30T20:15:00+08:00",
        freshness="fresh",
        plan_status="active",
        plan_budget=1200,
        spend=400,
        gmv=1000,
        orders=20,
        views=1000,
        online_viewers=120,
        roi=2.5,
        gpm=1000,
    )

    async def provider():
        return SnapshotReading(snapshot=snapshot, source="cdp")

    event = await AsyncMonitorService(provider).tick()

    assert event.source == "cdp"
    assert event.freshness == "fresh"
    assert event.metrics.roi == 2.5
    assert event.metrics.gpm == 1000
    assert event.metrics.online_viewers == 120
