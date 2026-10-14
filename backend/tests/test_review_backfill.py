# -*- coding: utf-8 -*-
"""复盘补跑：只有确认「旧场次已结束」才补，且不重复、不猜数据。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.review_backfill import (
    build_catch_up_review,
    group_sessions,
    missing_sessions,
    review_date_of,
    snapshot_from_report,
)

BEIJING = ZoneInfo("Asia/Shanghai")


def _log(room_id, started, created, spend=10000.0, roi=1.8, online=30):
    return {
        "source": "cdp",
        "live_room_id": room_id,
        "live_started_at": started,
        "created_at": created,
        "room_name": "质润官方旗舰店",
        "spend": spend,
        "gmv": spend * roi,
        "orders": int(spend / 100),
        "views": 5000,
        "online_viewers": online,
        "roi": roi,
        "gpm": 2000.0,
    }


def test_group_sessions_splits_by_room_id():
    logs = [
        _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T20:00:00+08:00"),
        _log("B", "2026-10-09T06:00:00+08:00", "2026-10-09T10:00:00+08:00"),
        _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T21:00:00+08:00"),
    ]
    sessions = group_sessions(logs)
    assert [s["key"] for s in sessions] == ["room:A", "room:B"]
    assert len(sessions[0]["reports"]) == 2


def test_records_without_session_identity_are_dropped():
    """既没有 live_room_id 也没有 live_started_at 的记录，不能归到"某一场"里。

    第一版补跑就是因为把它归成 unknown 组，把正在直播的场次切出一个"已结束的旧场次"。
    """
    logs = [
        {"source": "cdp", "created_at": "2026-10-10T09:00:00+08:00", "room_name": "质润官方旗舰店"},
        _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T21:00:00+08:00"),
    ]
    sessions = group_sessions(logs)
    assert len(sessions) == 1
    assert sessions[0]["key"] == "room:A"


def test_missing_sessions_skips_freshly_ended_session():
    """刚切场就补，会把还在播的场次误判成结束 —— 必须要求空闲 10 分钟以上。"""
    now = datetime(2026, 10, 9, 9, 0, tzinfo=BEIJING)
    logs = [
        # 10-08 场：早就结束了 → 该补
        _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T21:00:00+08:00"),
        # 10-09 早场：5 分钟前才停 → 这轮不补（可能还在播）
        _log("B", "2026-10-09T06:00:00+08:00", "2026-10-09T08:55:00+08:00"),
        # 新场次已经开播（不和时间重叠，专门用来隔离"太新"这一条规则）
        _log("C", "2026-10-09T08:58:00+08:00", "2026-10-09T08:59:00+08:00"),
    ]
    missing = missing_sessions(logs, set(), now=now)
    assert [m["date"] for m in missing] == ["2026-10-08"]


def test_missing_sessions_only_reports_ended_ones():
    logs = [
        _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T21:00:00+08:00"),
        _log("B", "2026-10-09T06:00:00+08:00", "2026-10-09T10:00:00+08:00"),
    ]
    # 只有一场（就是最新那场）→ 无法确定是否结束，不补
    assert missing_sessions([logs[0]], set()) == []
    # 出现更新的场次后，旧场次才补
    logs.append(_log("C", "2026-10-10T06:00:00+08:00", "2026-10-10T08:00:00+08:00"))
    missing = missing_sessions(logs, set())
    assert [m["date"] for m in missing] == ["2026-10-08", "2026-10-09"]
    # 已经有复盘的日期不再补
    assert [m["date"] for m in missing_sessions(logs, {"2026-10-08"})] == ["2026-10-09"]


def test_missing_sessions_skips_cdp_error_reports():
    logs = [
        {"source": "cdp-error", "created_at": "2026-10-08T21:00:00+08:00"},
        _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T20:00:00+08:00"),
        _log("B", "2026-10-09T06:00:00+08:00", "2026-10-09T10:00:00+08:00"),
        _log("C", "2026-10-10T06:00:00+08:00", "2026-10-10T08:00:00+08:00"),
    ]
    missing = missing_sessions(logs, set())
    assert ("2026-10-08" in [m["date"] for m in missing]) is True


def test_review_date_uses_live_start_not_log_time():
    session = {
        "live_started_at": "2026-10-08T23:30:00+08:00",
        "reports": [_log("A", "2026-10-08T23:30:00+08:00", "2026-10-09T02:30:00+08:00")],
    }
    # 场次跨天：日期要按开播时间（10-08），不能按结束时（10-09）
    assert review_date_of(session) == "2026-10-08"


def test_snapshot_from_report_does_not_invent_fields():
    report = _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T21:00:00+08:00")
    snap = snapshot_from_report(report)
    assert snap.spend == 10000.0
    assert snap.live_room_id == "A"
    # 报表里没有的字段必须是 None，不能补猜
    assert snap.exposure_count is None
    assert snap.view_count is None
    assert snap.product_clicks is None


def test_catch_up_review_is_marked_and_keeps_totals():
    from app.services.monitor import MonitorProfile

    session = {
        "key": "A",
        "room_name": "质润官方旗舰店",
        "live_started_at": "2026-10-08T18:42:00+08:00",
        "date": "2026-10-08",
        "reports": [
            _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T19:00:00+08:00", spend=8000, roi=1.7),
            _log("A", "2026-10-08T18:42:00+08:00", "2026-10-08T21:00:00+08:00", spend=12000, roi=1.9),
        ],
    }
    profile = MonitorProfile(
        version=1, business_direction="测试", primary_objective="测试", hard_constraints={"roi_target": 2.5}
    )
    review = build_catch_up_review(session, profile)
    markdown = review["report_markdown"]
    assert review["caught_up"] is True
    assert "本场复盘是补跑生成的" in markdown
    # 用最后一条盯盘记录的数，别把中间态当最终
    assert "¥12,000.00" in markdown
    assert "直播复盘" in markdown
    assert review["date"] == "2026-10-08"


def test_catch_up_review_date_comes_from_session_not_last_record():
    """场次最后几条记录可能读不到开播时间，日期不能因此算到第二天。"""
    from app.services.monitor import MonitorProfile

    last_without_start = _log("A", "2026-10-09T06:00:17+08:00", "2026-10-10T15:11:00+08:00")
    last_without_start["live_started_at"] = None   # 头部不渲染时就是这样
    session = {
        "key": "room:A",
        "room_name": "质润官方旗舰店",
        "live_started_at": "2026-10-09T06:00:17+08:00",
        "date": "2026-10-09",
        "reports": [last_without_start],
    }
    profile = MonitorProfile(
        version=1, business_direction="测试", primary_objective="测试", hard_constraints={"roi_target": 2.6}
    )
    review = build_catch_up_review(session, profile)
    assert review["date"] == "2026-10-09"
    assert "直播复盘｜2026-10-09" in review["report_markdown"]
