from pathlib import Path

import pytest

from app.services.monitor import MonitorService


@pytest.fixture
def monitor_service():
    return MonitorService(Path("tests/fixtures/plan_live_snapshot.json"), profile_version=1)


def test_monitor_emits_profile_and_freshness(monitor_service):
    event = monitor_service.tick()
    assert event.profile_version >= 1
    assert event.freshness in {"fresh", "stale"}
    assert "策略画像" in event.banner