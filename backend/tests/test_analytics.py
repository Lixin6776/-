from pathlib import Path

import pytest

from app.execution.cdp.fixture_adapter import FixturePageAdapter
from app.services.analytics import AnalyticsService


def test_fixture_metrics_are_computed():
    snapshot = FixturePageAdapter().read_snapshot(Path("tests/fixtures/plan_live_snapshot.json"))
    metrics = AnalyticsService().compute(snapshot)
    assert metrics.roi == 2.5
    assert metrics.gpm == 1000
    assert metrics.spend == 400


def test_malformed_snapshot_fails_closed(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"freshness":"fresh"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed page snapshot"):
        FixturePageAdapter().read_snapshot(path)