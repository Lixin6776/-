# -*- coding: utf-8 -*-
"""操作净效应：分类 + 结构 + 护栏（样本不足不给结论）。"""

from datetime import datetime, timedelta, timezone

from app.services.ops_outcome import classify_operation, compute_ops_outcome

BJ = timezone(timedelta(hours=8))


def test_classify_operation_covers_common_types():
    assert classify_operation({"summary": "调控状态：调控中 -> 已暂停"}) == "暂停追投"
    assert classify_operation({"details": ["调控预算：3000.00元 -> 100.00元"]}) == "降追投预算"
    assert classify_operation({"details": ["调控预算：1000.00元 -> 3000.00元"]}) == "加追投预算"
    assert (
        classify_operation({"type": "新建", "summary": "操作：素材追投；调控预算：2000.00元"})
        == "新建追投"
    )
    assert classify_operation({"summary": "综合营销ROI目标：3 -> 2.80"}) == "ROI目标调整"
    assert classify_operation({"summary": "增加视频ID: 123,456"}) == "加素材"
    assert classify_operation({"summary": "完全看不懂的东西"}) == "其他"


def _report(minute: int, spend: float, gmv: float, ops=None):
    at = datetime(2026, 10, 10, 8, 0, tzinfo=BJ) + timedelta(minutes=5 * minute)
    return {
        "source": "cdp",
        "created_at": at.isoformat(),
        "spend": spend,
        "gmv": gmv,
        "platform_operations": ops or [],
    }


def _op(minute: int, summary: str, kind: str = "修改"):
    at = datetime(2026, 10, 10, 8, 0, tzinfo=BJ) + timedelta(minutes=5 * minute)
    return {"time": at.strftime("%Y-%m-%d %H:%M:%S"), "type": kind, "summary": summary, "details": []}


def test_compute_ops_outcome_structure_and_sample_guard():
    logs = []
    for i in range(12):
        logs.append(_report(i, spend=1000 + i * 300, gmv=2000 + i * 750))
    # 在第 6 个时刻做一次"加追投预算"
    logs[6]["platform_operations"] = [_op(6, "调控预算：3000.00元 -> 4000.00元")]

    result = compute_ops_outcome(logs)
    assert result["window_minutes"] == 10
    assert result["min_sample"] == 20
    assert "baseline" in result and "operations" in result and "velocity_strata" in result
    # 只有 1 个操作样本 → 必须标"样本不足"，不能给结论
    op = next((x for x in result["operations"] if x["operation"] == "加追投预算"), None)
    assert op is not None
    assert op["verdict"] == "insufficient"
