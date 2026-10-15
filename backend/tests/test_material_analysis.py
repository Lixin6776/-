import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.execution.cdp.material_reader import (
    build_material_query_body,
    parse_material_list_response,
)
from app.services.action_planner import PlanSnapshot
from app.services.analytics import ComputedMetrics
from app.services.material_analysis import (
    MaterialAnalysisStore,
    MaterialMetric,
    build_material_analysis,
)
from app.services.monitor import MonitorEvent


def _event() -> MonitorEvent:
    return MonitorEvent(
        captured_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        freshness="fresh",
        banner="长期策略：稳定放量；目标：ROI >= 2.5；约束：日预算上限 5000",
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


def _material_row(
    material_id: str,
    name: str,
    spend: float,
    roi: float,
    gmv: float,
    orders: int,
    tags: list[str] | None = None,
) -> dict:
    tags = tags or ["品牌视频"]
    return {
        "dimensions": {
            "materialId": {"value": material_id, "valueStr": material_id},
            "roi2MaterialVideoName": {"value": name, "valueStr": name},
            "materialTagList": {
                "value": json.dumps(tags, ensure_ascii=False),
                "valueStr": json.dumps(tags, ensure_ascii=False),
            },
            "roi2MaterialUploadTime": {
                "value": "2026-09-30 10:00:00",
                "valueStr": "2026-09-30 10:00:00",
            },
        },
        "metrics": {
            "statCostForRoi2": {"value": spend, "valueStr": f"{spend:.2f}"},
            "totalPrepayAndPaySettleOverallRoi21H": {
                "value": roi,
                "valueStr": f"{roi:.2f}",
            },
            "totalPayOrderGmvIncludeCouponForRoi2": {
                "value": gmv,
                "valueStr": f"{gmv:.2f}",
            },
            "totalPayOrderCountForRoi2": {"value": orders, "valueStr": str(orders)},
            "totalCostPerPayOrderForRoi2": {
                "value": spend / orders,
                "valueStr": f"{spend / orders:.2f}",
            },
            "liveCvrRateForRoi2V2": {"value": 4.2, "valueStr": "4.20%"},
            "liveConvertRateForRoi2V2": {"value": 2.8, "valueStr": "2.80%"},
        },
        "fields": {},
    }


def test_parse_material_list_response_maps_core_metrics():
    payload = {
        "status_code": 0,
        "data": {
            "statsData": {
                "rows": [
                    _material_row(
                        "7690408383316754468",
                        "种草-复刻-热点型-新品桌搭",
                        7795.8,
                        1.6,
                        13643.33,
                        84,
                        ["品牌视频", "唐"],
                    )
                ],
                "totalCount": "1225",
            }
        },
    }

    materials = parse_material_list_response(payload)

    assert len(materials) == 1
    assert materials[0].material_id == "7690408383316754468"
    assert materials[0].name == "种草-复刻-热点型-新品桌搭"
    assert materials[0].spend == 7795.8
    assert materials[0].roi == 1.6
    assert materials[0].gmv == 13643.33
    assert materials[0].orders == 84
    assert materials[0].tags == ("品牌视频", "唐")


def test_build_material_query_body_uses_selected_date_and_page_size():
    template = {
        "StartTime": "2026-09-29 00:00:00",
        "EndTime": "2026-09-29 23:59:59",
        "PageParams": {"Limit": 10, "Offset": 30},
        "OrderBy": [{"Type": 2, "Field": "stat_cost_for_roi2"}],
        "Filters": {"Conditions": [{"Field": "anchor_id", "Values": ["123"]}]},
    }

    body = build_material_query_body(template, date(2026, 10, 1), limit=50)

    assert body["StartTime"] == "2026-10-01 00:00:00"
    assert body["EndTime"] == "2026-10-01 23:59:59"
    assert body["PageParams"] == {"Limit": 50, "Offset": 0}
    assert template["StartTime"] == "2026-09-29 00:00:00"


def test_material_analysis_contains_new_material_direction():
    report = build_material_analysis(
        PlanSnapshot(id="plan-1", name="计划一", status="active", budget=5000, roi_goal=2.5),
        _event(),
        datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
    )

    assert report["date"] == "2026-10-01"
    assert "素材分析报告" in report["report_markdown"]
    assert "素材产出方向" in report["report_markdown"]
    assert "痛点、效果演示、真实反馈" in report["report_markdown"]


def test_material_analysis_uses_per_material_metrics():
    report = build_material_analysis(
        PlanSnapshot(id="plan-1", name="计划一", status="active", budget=5000, roi_goal=2.5),
        _event(),
        datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
        materials=[
            MaterialMetric(
                material_id="winner",
                name="高转化痛点开场",
                spend=5000,
                roi=3.1,
                gmv=15500,
                orders=100,
                order_cost=50,
                ctr=5.2,
                conversion_rate=3.4,
                tags=("品牌视频", "痛点"),
            ),
            MaterialMetric(
                material_id="loser",
                name="泛品牌口播",
                spend=4500,
                roi=1.1,
                gmv=4950,
                orders=35,
                order_cost=128.6,
                ctr=1.8,
                conversion_rate=1.5,
                tags=("品牌视频",),
            ),
        ],
    )

    markdown = report["report_markdown"]
    assert "### 一、每日素材消耗概况" in markdown
    assert "### 二、新素材情况" in markdown
    assert "### 三、跑量素材较上一日变化" in markdown
    assert "### 四、素材产出方向" in markdown
    assert "高转化痛点开场" in markdown
    assert "泛品牌口播" in markdown
    assert "长期策略约束" in markdown
    assert report["metrics"]["material_count"] == 2


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

@pytest.mark.asyncio
async def test_material_analysis_job_returns_generated_report(tmp_path):
    from types import SimpleNamespace

    from app.main import run_material_analysis_job

    class FakeReader:
        async def read(self, _analysis_date):
            return [
                MaterialMetric(
                    material_id="winner",
                    name="高转化痛点开场",
                    spend=5000,
                    roi=3.1,
                    gmv=15500,
                    orders=100,
                )
            ]

    class FakeHub:
        async def publish(self, _payload):
            return None

    state = SimpleNamespace(
        latest_plan_snapshot=PlanSnapshot(
            id="plan-1",
            name="计划一",
            status="active",
            budget=5000,
            roi_goal=2.5,
        ),
        monitor_service=SimpleNamespace(latest_event=lambda: _event()),
        material_analysis_store=MaterialAnalysisStore(tmp_path / "materials.json"),
        notification_hub=FakeHub(),
        material_reader=FakeReader(),
    )

    report = await run_material_analysis_job(SimpleNamespace(state=state))

    assert report["id"]
    assert "高转化痛点开场" in report["report_markdown"]


def test_material_analysis_store_replaces_placeholder_with_material_data(tmp_path):
    store = MaterialAnalysisStore(tmp_path / "materials.json")
    store.add_if_absent(
        {"id": "placeholder", "date": "2026-10-01", "metrics": {"material_count": 0}}
    )

    replacement = store.add_if_absent(
        {"id": "detailed", "date": "2026-10-01", "metrics": {"material_count": 50}}
    )

    assert replacement["id"] == "detailed"
    assert store.list_analyses()[0]["id"] == "detailed"


def test_material_analysis_reports_daily_new_material_and_change_summary():
    current = [
        MaterialMetric(
            material_id="new",
            name="新素材-痛点开场",
            spend=1200,
            roi=2.8,
            gmv=3360,
            orders=18,
            created_at="2026-10-02 09:00:00",
        ),
        MaterialMetric(
            material_id="scale",
            name="跑量素材-场景演示",
            spend=2500,
            roi=2.2,
            gmv=5500,
            orders=30,
            created_at="2026-09-20 09:00:00",
        ),
        MaterialMetric(
            material_id="decline",
            name="下降素材-泛口播",
            spend=300,
            roi=0.9,
            gmv=270,
            orders=2,
            created_at="2026-09-10 09:00:00",
        ),
    ]
    previous = [
        MaterialMetric(material_id="scale", name="跑量素材-场景演示", spend=1500),
        MaterialMetric(material_id="decline", name="下降素材-泛口播", spend=1000),
        MaterialMetric(material_id="stopped", name="停止素材-旧视频", spend=800),
    ]

    report = build_material_analysis(
        PlanSnapshot(id="plan-1", name="计划一", status="active", budget=5000, roi_goal=2.5),
        _event(),
        report_date=date(2026, 10, 2),
        materials=current,
        previous_materials=previous,
    )

    markdown = report["report_markdown"]
    assert "每日素材消耗概况" in markdown
    assert "新素材上新：1 条" in markdown
    assert "新素材消耗：¥1,200.00" in markdown
    assert "跑量素材较上一日变化" in markdown
    assert "增长素材" in markdown
    assert "下降素材" in markdown
    assert "停止消耗素材" in markdown
    assert "跑量素材-场景演示" in markdown
    assert "停止素材-旧视频" in markdown
    assert report["metrics"]["new_material_count"] == 1
    assert report["metrics"]["new_material_spend"] == 1200


@pytest.mark.asyncio
async def test_generate_material_analysis_reads_previous_day(tmp_path):

    from app.services.material_analysis import generate_and_publish_material_analysis

    class FakeMonitor:
        def latest_event(self):
            return _event()

    class FakeHub:
        async def publish(self, _payload):
            return None

    class FakeReader:
        def __init__(self):
            self.dates = []

        async def read(self, analysis_date):
            self.dates.append(analysis_date)
            if analysis_date == date(2026, 10, 2):
                return [MaterialMetric(material_id="new", name="新素材", spend=100, created_at="2026-10-02 08:00:00")]
            return [MaterialMetric(material_id="old", name="旧素材", spend=200)]

    reader = FakeReader()
    report = await generate_and_publish_material_analysis(
        FakeMonitor(),
        lambda: PlanSnapshot(id="plan-1", name="计划一", status="active", budget=5000, roi_goal=2.5),
        MaterialAnalysisStore(tmp_path / "materials.json"),
        FakeHub(),
        material_reader=reader,
        analysis_date=date(2026, 10, 2),
    )

    assert reader.dates == [date(2026, 10, 2), date(2026, 10, 1)]
    assert "较上一日" in report["report_markdown"]


def test_material_analysis_store_lists_newest_first(tmp_path):
    """UI 顶部必须是最新报告 —— 不能因为写入顺序让老报告排前面。"""
    store = MaterialAnalysisStore(tmp_path / "materials.json")
    store.add_if_absent({"id": "old", "date": "2026-10-01", "metrics": {"material_count": 1}})
    store.add_if_absent({"id": "new", "date": "2026-10-14", "metrics": {"material_count": 50}})
    store.add_if_absent({"id": "mid", "date": "2026-10-07", "metrics": {"material_count": 50}})

    assert [i["date"] for i in store.list_analyses()] == [
        "2026-10-14",
        "2026-10-07",
        "2026-10-01",
    ]
    assert store.latest()["id"] == "new"


@pytest.mark.asyncio
async def test_material_reader_connect_retries_then_succeeds(monkeypatch):
    """connect_over_cdp 卡住/失败时要快速重试，而不是干等 3 分钟。"""
    from app.execution.cdp import material_reader as mr

    monkeypatch.setattr(mr.asyncio, "sleep", lambda *_: _noop())

    class FakeChromium:
        def __init__(self):
            self.calls = 0

        async def connect_over_cdp(self, endpoint, timeout=None):
            self.calls += 1
            assert timeout == mr.CDP_CONNECT_TIMEOUT_MS
            if self.calls < 2:
                raise RuntimeError("transient")
            return "browser"

    class FakePW:
        def __init__(self):
            self.chromium = FakeChromium()

    reader = mr.CdpMaterialReader.__new__(mr.CdpMaterialReader)
    reader.endpoint = "http://127.0.0.1:9222"
    pw = FakePW()
    result = await reader._connect(pw)
    assert result == "browser"
    assert pw.chromium.calls == 2


async def _noop():
    return None


def test_material_analysis_uses_server_total_spend():
    """总消耗必须用服务端聚合值 —— 明细只有前 N 条，求和会少算（实测约 10%）。"""
    materials = [
        MaterialMetric(material_id="a", name="A", spend=1000, roi=2.0, gmv=2000, orders=10),
        MaterialMetric(material_id="b", name="B", spend=500, roi=1.5, gmv=750, orders=5),
    ]
    report = build_material_analysis(
        PlanSnapshot(id="p", name="计划一", status="active", budget=5000, roi_goal=2.5),
        _event(),
        report_date=date(2026, 10, 14),
        materials=materials,
        server_total_spend=9999.0,
    )
    assert report["metrics"]["total_material_spend"] == 9999.0
    assert report["metrics"]["sampled_material_spend"] == 1500.0
    assert "¥9,999.00" in report["report_markdown"]


@pytest.mark.asyncio
async def test_generate_prefers_read_with_total(tmp_path):
    """reader 支持 read_with_total 时要用它拿服务端总额。"""
    from app.services.material_analysis import generate_and_publish_material_analysis

    class FakeReader:
        async def read(self, _d):
            raise AssertionError("不该调用 read()")

        async def read_with_total(self, _d):
            return (
                [MaterialMetric(material_id="a", name="A", spend=1000, roi=2.0, gmv=2000, orders=10)],
                8888.0,
            )

    class FakeHub:
        async def publish(self, _payload):
            return None

    store = MaterialAnalysisStore(tmp_path / "materials.json")
    report = await generate_and_publish_material_analysis(
        SimpleNamespace(latest_event=lambda: _event()),
        lambda: PlanSnapshot(id="p", name="计划一", status="active", budget=5000, roi_goal=2.5),
        store,
        FakeHub(),
        material_reader=FakeReader(),
        analysis_date=date(2026, 10, 14),
    )
    assert report["metrics"]["total_material_spend"] == 8888.0


def test_store_replaces_when_total_spend_improves(tmp_path):
    """同一天、素材数相同但总消耗更高（数据更全）时，要替换旧报告。"""
    store = MaterialAnalysisStore(tmp_path / "materials.json")
    store.add_if_absent(
        {"id": "old", "date": "2026-10-14", "metrics": {"material_count": 50, "total_material_spend": 25779.37}}
    )
    replacement = store.add_if_absent(
        {"id": "new", "date": "2026-10-14", "metrics": {"material_count": 50, "total_material_spend": 28756.76}}
    )
    assert replacement["id"] == "new"
    assert store.latest()["id"] == "new"

    # 更差的（消耗更低）不能覆盖
    worse = store.add_if_absent(
        {"id": "worse", "date": "2026-10-14", "metrics": {"material_count": 50, "total_material_spend": 100.0}}
    )
    assert worse["id"] == "new"


@pytest.mark.asyncio
async def test_material_analysis_job_regenerates_stale_report(tmp_path):
    """旧格式报告（没有 sampled_material_count）要重算一次，用上服务端精确总额。"""
    from app.main import run_material_analysis_job

    store = MaterialAnalysisStore(tmp_path / "materials.json")
    store.add_if_absent(
        {
            "id": "old",
            "date": "2026-10-14",
            "metrics": {"material_count": 50, "total_material_spend": 25779.37},
        }
    )

    class FakeReader:
        def __init__(self):
            self.calls = 0

        async def read(self, _d):
            raise AssertionError("应走 read_with_total")

        async def read_with_total(self, _d):
            self.calls += 1
            return (
                [MaterialMetric(material_id="a", name="素材A", spend=1000, roi=2.0, gmv=2000, orders=10)],
                28756.76,
            )

    class FakeHub:
        async def publish(self, _payload):
            return None

    reader = FakeReader()
    state = SimpleNamespace(
        latest_plan_snapshot=PlanSnapshot(id="plan-1", name="计划一", status="active", budget=5000, roi_goal=2.5),
        monitor_service=SimpleNamespace(latest_event=lambda: _event()),
        material_analysis_store=store,
        notification_hub=FakeHub(),
        material_reader=reader,
    )
    report = await run_material_analysis_job(SimpleNamespace(state=state), analysis_date=date(2026, 10, 14))

    assert reader.calls == 1
    assert report["metrics"]["total_material_spend"] == 28756.76


@pytest.mark.asyncio
async def test_material_analysis_job_reuses_fresh_report(tmp_path):
    """已经是新格式的报告，不能重复重算（否则每次调用都白读一遍）。"""
    from app.main import run_material_analysis_job

    store = MaterialAnalysisStore(tmp_path / "materials.json")
    store.add_if_absent(
        {
            "id": "fresh",
            "date": "2026-10-14",
            "metrics": {
                "report_schema": 3,
                "material_count": 50,
                "sampled_material_count": 50,
                "total_material_spend": 28756.76,
            },
        }
    )

    class FakeReader:
        async def read_with_total(self, _d):
            raise AssertionError("不该重算")

    state = SimpleNamespace(
        latest_plan_snapshot=PlanSnapshot(id="plan-1", name="计划一", status="active", budget=5000, roi_goal=2.5),
        monitor_service=SimpleNamespace(latest_event=lambda: _event()),
        material_analysis_store=store,
        notification_hub=None,
        material_reader=FakeReader(),
    )
    report = await run_material_analysis_job(SimpleNamespace(state=state), analysis_date=date(2026, 10, 14))
    assert report["id"] == "fresh"


def test_material_analysis_prefers_day_metrics():
    """账户口径要用目标那天的读数，而不是"最近一次盯盘读数"（口径必须对齐）。"""
    from app.services.analytics import ComputedMetrics

    day = ComputedMetrics(
        roi=2.47, gpm=2025.0, spend=38725.68, gmv=95642.25,
        orders=523, online_viewers=41, views=29824,
    )
    report = build_material_analysis(
        PlanSnapshot(id="p", name="计划一", status="active", budget=5000, roi_goal=2.8),
        _event(),
        report_date=date(2026, 10, 14),
        materials=[MaterialMetric(material_id="a", name="A", spend=1000, roi=2.0, gmv=2000, orders=10)],
        day_metrics=day,
    )
    assert report["metrics"]["spend"] == 38725.68
    assert report["metrics"]["roi"] == 2.47
    assert "¥38,725.68" in report["report_markdown"]


def test_day_account_metrics_picks_target_day_last_reading(tmp_path):
    from app.main import _day_account_metrics
    from app.services.watch_log_store import SqliteWatchLogStore

    store = SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json")
    store.append({"id": "1", "source": "cdp", "created_at": "2026-10-14T10:00:00+08:00",
                  "roi": 1.0, "spend": 100.0, "gmv": 100.0, "orders": 1,
                  "online_viewers": 5, "views": 50, "gpm": 2000.0})
    store.append({"id": "2", "source": "cdp", "created_at": "2026-10-14T20:00:00+08:00",
                  "roi": 2.47, "spend": 38725.68, "gmv": 95642.25, "orders": 523,
                  "online_viewers": 41, "views": 29824, "gpm": 2025.0})
    store.append({"id": "3", "source": "cdp", "created_at": "2026-10-15T09:00:00+08:00",
                  "roi": 9.9, "spend": 99999.0, "gmv": 1.0, "orders": 1,
                  "online_viewers": 1, "views": 1, "gpm": 1.0})

    app = SimpleNamespace(state=SimpleNamespace(live_watch_service=SimpleNamespace(store=store)))
    m = _day_account_metrics(app, date(2026, 10, 14))
    assert m is not None
    assert m.spend == 38725.68     # 取的是 10-14 当天最后一条，不是 10-15
    assert m.roi == 2.47
    assert m.orders == 523
