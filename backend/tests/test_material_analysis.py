import json
from datetime import UTC, date, datetime

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