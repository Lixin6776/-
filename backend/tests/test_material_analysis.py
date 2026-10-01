from datetime import UTC, datetime

import pytest

from app.services.action_planner import PlanSnapshot
from app.services.analytics import ComputedMetrics
from app.services.material_analysis import MaterialAnalysisStore, build_material_analysis
from app.services.monitor import MonitorEvent


def _event() -> MonitorEvent:
    return MonitorEvent(
        captured_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        freshness="fresh",
        banner="test",
        level="normal",
        reason="指标正常",
        profile_version=1,
        metrics=ComputedMetrics(
            roi=1.8,
            gpm=3000,
            spend=10000,
            gmv=18000,
            orders=100,
            online_viewers=20,
            views=5000,
        ),
        plan_status="active",
        plan_budget=5000,
        source="cdp",
    )


def test_material_analysis_contains_new_material_direction():
    report = build_material_analysis(
        PlanSnapshot(id="plan-1", name="计划一", status="active", budget=5000, roi_goal=2.5),
        _event(),
        datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
    )

    assert report["date"] == "2026-10-01"
    assert "素材分析报告" in report["report_markdown"]
    assert "新素材制作方向" in report["report_markdown"]
    assert "痛点、效果演示、真实反馈" in report["report_markdown"]


def test_material_analysis_store_deduplicates_same_date(tmp_path):
    store = MaterialAnalysisStore(tmp_path / "materials.json")
    first = store.add_if_absent({"id": "1", "date": "2026-10-01", "report_markdown": "a"})
    second = store.add_if_absent({"id": "2", "date": "2026-10-01", "report_markdown": "b"})

    assert first["id"] == "1"
    assert second["id"] == "1"
    assert len(store.list_analyses()) == 1


@pytest.mark.asyncio
async def test_generate_material_analysis_publishes_to_hub(tmp_path):
    from app.services.material_analysis import generate_and_publish_material_analysis

    class FakeMonitor:
        def latest_event(self):
            return _event()

    class FakeHub:
        def __init__(self):
            self.payloads = []

        async def publish(self, payload):
            self.payloads.append(payload)

    store = MaterialAnalysisStore(tmp_path / "materials.json")
    hub = FakeHub()
    report = await generate_and_publish_material_analysis(
        FakeMonitor(),
        lambda: PlanSnapshot(id="plan-1", name="计划一", status="active", budget=5000, roi_goal=2.5),
        store,
        hub,
    )

    assert report["report_markdown"] in hub.payloads[0]["message"]
    assert hub.payloads[0]["type"] == "material_analysis"
