# -*- coding: utf-8 -*-
"""盯盘自检：换场要先复读确认；跨源偏差要显式写进自检区。"""

import asyncio

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.services.analytics import ComputedMetrics
from app.services.live_watch import LiveWatchService
from app.services.monitor import MonitorEvent
from app.services.watch_log_store import SqliteWatchLogStore

from datetime import UTC, datetime


class _Hub:
    def __init__(self):
        self.events = []

    async def publish(self, payload):
        self.events.append(payload)


class _Monitor:
    def __init__(self, event):
        self._event = event

    def tick(self):
        return self._event


def _event(roi=1.8, spend=10000.0, started=None):
    return MonitorEvent(
        captured_at=datetime(2026, 10, 11, 0, 30, tzinfo=UTC),
        freshness="fresh",
        banner="",
        level="normal",
        reason="指标正常",
        profile_version=1,
        metrics=ComputedMetrics(
            roi=roi, gpm=2000.0, spend=spend, gmv=spend * roi, orders=50,
            online_viewers=30, views=5000,
        ),
        plan_status="active",
        plan_budget=0.0,
        source="cdp",
        spend_delta=120.0,
        minutes_since_previous=5.0,
        live_started_at=started,
    )


def _snapshot(started):
    return MetricSnapshot(
        captured_at=datetime(2026, 10, 11, 0, 30, tzinfo=UTC),
        live_started_at=started,
        freshness="fresh",
        plan_status="active",
        plan_budget=0.0,
        spend=10000.0,
        gmv=18000.0,
        orders=50,
        views=5000,
        online_viewers=30,
        roi=1.8,
        gpm=2000.0,
    )


OLD = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)
NEW = datetime(2026, 10, 11, 6, 0, tzinfo=UTC)


def _service(tmp_path, event, hub, refresher=None, split_provider=None):
    return LiveWatchService(
        _Monitor(event),
        hub,
        store=SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json"),
        snapshot_refresher=refresher,
        spend_split_provider=split_provider,
        state_path=tmp_path / "state.json",
        interval_seconds=300,
    )


def test_session_switch_is_confirmed_by_reread(tmp_path):
    hub = _Hub()

    async def refresher():
        return _snapshot(NEW)      # 复读还是新场次 → 确认真换场

    service = _service(tmp_path, _event(started=NEW), hub, refresher)
    service._last_live_started = OLD
    report = asyncio.run(service.tick_once())

    assert any(e.get("type") == "session_started" for e in hub.events)
    assert "确认换场" in report["report_markdown"]


def test_session_switch_jitter_is_ignored(tmp_path):
    """复读发现还在上一场 → 说明刚才是误读，不能清空聊天记录、也不能切场。"""
    hub = _Hub()

    async def refresher():
        return _snapshot(OLD)      # 复读回到上一场

    service = _service(tmp_path, _event(started=NEW), hub, refresher)
    service._last_live_started = OLD
    report = asyncio.run(service.tick_once())

    assert not any(e.get("type") == "session_started" for e in hub.events)
    assert "已忽略这次抖动" in report["report_markdown"]


def test_cross_source_roi_gap_is_reported(tmp_path):
    """大屏 ROI 与素材口径 ROI 差得多时，自检区要写出来（不是拿它判错，是提示口径不同）。"""
    hub = _Hub()

    async def split_provider(session_start=None):
        return {
            "total_spend": 8000.0,
            "basic_spend": 3000.0,
            "assist_spend": 5000.0,
            "split": {"total_roi": 2.4, "basic_roi": 3.0, "assist_roi": 2.0,
                      "total_spend": 8000.0, "basic_spend": 3000.0, "assist_spend": 5000.0,
                      "split_window": {"start": "x", "end": "y"}},
        }

    service = _service(
        tmp_path, _event(roi=1.8), hub, refresher=None, split_provider=split_provider
    )
    report = asyncio.run(service.tick_once())
    text = report["report_markdown"]

    assert "跨源偏差" in text          # ROI 1.82 vs 2.40 → 差 32%
    assert "口径覆盖" in text          # 素材口径 8000 只覆盖大屏 10000 的 80%


# --- 本场结束：出复盘 + 自动停盯盘（下一场手动开）-----------------------------

def test_session_end_triggers_review_and_stops_watch(tmp_path):
    hub = _Hub()
    ended_calls = []

    async def end_handler(room, started):
        ended_calls.append((room, started))

    service = LiveWatchService(
        _Monitor(_event(started=NEW)),   # 大屏明确说已结束
        hub,
        store=SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json"),
        session_end_handler=end_handler,
        state_path=tmp_path / "state.json",
        interval_seconds=300,
    )
    service._last_live_started = NEW

    async def run_once():
        # 直接把这一轮跑完（_run 里的停机分支在 tick 之后判断）
        service._pending_stop_reason = None
        report = await service.tick_once()
        return report

    # 让 event.plan_status == "ended" 才算结束
    service.monitor_service = _Monitor(
        _event(started=NEW).model_copy(update={"plan_status": "ended"})
    )
    report = asyncio.run(run_once())

    # 复盘回调被调用了（room 由快照带，这里的事件对象没有，重点看开播时间对不对）
    assert len(ended_calls) == 1
    assert ended_calls[0][1] == NEW
    # 报表里说清楚会自动停
    assert "盯盘按你的要求自动停止" in report["report_markdown"]
    # 停机指令已经挂上（_run 会在 tick 结束后执行）
    assert service._pending_stop_reason is not None
    assert "手动开始" in service._pending_stop_reason


def test_tick_timeout_is_configured(tmp_path):
    service = LiveWatchService(
        _Monitor(_event()),
        _Hub(),
        store=SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json"),
        state_path=tmp_path / "state.json",
    )
    # 一轮读取必须有整体超时，否则某个 await 卡住会把循环拖死
    assert 30 <= service.tick_timeout_seconds <= 180
