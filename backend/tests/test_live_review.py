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


def _review_for(profile, snapshot=None):
    snapshot = snapshot or _snapshot()
    metrics = AnalyticsService().compute(snapshot)
    return build_live_review(snapshot, metrics, profile, snapshot.captured_at)


def test_build_live_review_contains_review_and_next_session_plan():
    profile = MonitorProfile(
        version=1,
        business_direction="ROI目标 2.5",
        primary_objective="提升成交额",
        hard_constraints={"roi_target": 2.5},
    )

    review = _review_for(profile)
    report = review["report_markdown"]

    assert review["date"] == "2026-10-01"
    assert "直播复盘" in report
    # 结论层：说清达标与否、缺口多少
    assert "综合营销 ROI：1.80（目标 2.50，**未达标**）" in report
    # 复盘结构：数据拆解 / 流量结构 / 问题归因 / 落地动作 / 下场准备
    assert "### 二、数据拆解" in report
    assert "### 三、直播间流量结构" in report
    assert "### 四、具体问题（现象 → 归因）" in report
    assert "### 五、具体解决方案（落到操作）" in report
    assert "### 六、下场开播前准备" in report
    # 问题必须落到可执行动作，而不是只说「有问题」
    assert "**现象**" in report and "**归因（按可能性排序）**" in report
    assert "本场无需要调整的动作" not in report
    assert "所有动作都需你确认后执行" in report
    assert "必须人工确认后再执行" in report


def test_live_review_store_deduplicates_same_date(tmp_path):
    store = LiveReviewStore(tmp_path / "reviews.json")
    first = store.add_if_absent({"id": "1", "date": "2026-10-01", "report_markdown": "a"})
    second = store.add_if_absent({"id": "2", "date": "2026-10-01", "report_markdown": "b"})

    assert first["id"] == "1"
    assert second["id"] == "1"
    assert len(store.list_reviews()) == 1


def test_review_store_lists_newest_first(tmp_path):
    """UI 顶部必须是最新复盘 —— 补跑/跨天分段会让文件顺序乱掉。"""
    store = LiveReviewStore(tmp_path / "reviews.json")
    store.add_if_absent({"id": "old", "date": "2026-10-01", "report_markdown": "a"})
    store.add_if_absent({"id": "new", "date": "2026-10-14", "report_markdown": "b"})
    store.add_if_absent({"id": "mid", "date": "2026-10-07", "report_markdown": "c"})

    assert [r["date"] for r in store.list_reviews()] == [
        "2026-10-14",
        "2026-10-07",
        "2026-10-01",
    ]
    assert store.latest()["date"] == "2026-10-14"


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
    report = review["report_markdown"]

    assert review["date"] == "2026-09-30"
    # 目标未配置时要如实说「未配置」，不能编一个目标出来算缺口
    assert "综合营销 ROI：1.80（目标 --，**未配置**）" in report
    assert "未配置目标 ROI，**无法判断是否达标**" in report
    assert "目标 2.00" not in report