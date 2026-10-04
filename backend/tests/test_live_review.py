from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.services.analytics import AnalyticsService
from app.services.live_review import LiveReviewStore, build_live_review
from app.services.monitor import MonitorProfile


def _snapshot() -> MetricSnapshot:
    return MetricSnapshot(
        captured_at=datetime(2026, 10, 1, 15, 30, tzinfo=UTC),
        freshness="fresh",
        plan_status="ended",
        plan_budget=5000,
        spend=4200,
        gmv=7560,
        orders=63,
        views=1800,
        online_viewers=0,
        roi=1.8,
        gpm=4200,
    )


def test_build_live_review_contains_review_and_tomorrow_plan():
    snapshot = _snapshot()
    metrics = AnalyticsService().compute(snapshot)
    profile = MonitorProfile(
        version=1,
        business_direction="ROI目标 2.5",
        primary_objective="提升成交额",
        hard_constraints={"roi_target": 2.5},
    )

    review = build_live_review(snapshot, metrics, profile, snapshot.captured_at)

    assert review["date"] == "2026-10-01"
    assert "直播复盘" in review["report_markdown"]
    assert "综合营销 ROI：1.80" in review["report_markdown"]
    assert "未达标" in review["report_markdown"]
    assert "明日投放策略" in review["report_markdown"]
    assert "必须先经过人工确认" in review["report_markdown"]


def test_live_review_store_deduplicates_same_date(tmp_path):
    store = LiveReviewStore(tmp_path / "reviews.json")
    first = store.add_if_absent({"id": "1", "date": "2026-10-01", "report_markdown": "a"})
    second = store.add_if_absent({"id": "2", "date": "2026-10-01", "report_markdown": "b"})

    assert first["id"] == "1"
    assert second["id"] == "1"
    assert len(store.list_reviews()) == 1


def test_build_live_review_uses_live_start_date_and_reports_unknown_target():
    snapshot = MetricSnapshot(
        captured_at=datetime(2026, 10, 4, 12, 0, tzinfo=UTC),
        live_started_at=datetime(2026, 9, 30, 6, 0, 51, tzinfo=ZoneInfo("Asia/Shanghai")),
        freshness="fresh",
        plan_status="ended",
        plan_budget=9999999,
        spend=287165.42,
        gmv=517076.75,
        orders=3515,
        views=83507,
        online_viewers=0,
        roi=1.8,
        gpm=2872.77,
    )
    metrics = AnalyticsService().compute(snapshot)
    profile = MonitorProfile(
        version=0,
        business_direction="未配置",
        primary_objective="请先创建投放策略",
        hard_constraints={},
    )

    review = build_live_review(snapshot, metrics, profile, snapshot.captured_at)

    assert review["date"] == "2026-09-30"
    assert "- ROI 目标：--" in review["report_markdown"]
    assert "是否达标：未配置" in review["report_markdown"]