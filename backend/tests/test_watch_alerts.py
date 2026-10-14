# -*- coding: utf-8 -*-
"""盯盘异常告警：读不到数据 / 数据停滞要主动告警，但同类问题不能每 5 分钟刷屏。"""

import asyncio

from app.services.live_watch import LiveWatchService
from app.services.watch_log_store import SqliteWatchLogStore


def _service(tmp_path, sent: list):
    async def notifier(title, body):
        sent.append((title, body))

    service = LiveWatchService(
        None,
        None,
        store=SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json"),
        alert_notifier=notifier,
        # 必须隔离状态文件，否则会读到真实运行时的 state（里面有真实直播间/读数时间）
        state_path=tmp_path / "state.json",
    )
    return service


class _Event:
    reason = "CDP page not found for marker: board-next"


def test_alert_fires_once_per_condition(tmp_path):
    sent: list = []
    service = _service(tmp_path, sent)
    broken = {"source": "cdp-error", "room_name": "质润官方旗舰店", "note": "CDP 读取失败"}

    asyncio.run(service._maybe_alert(broken, _Event(), stagnant=False))
    asyncio.run(service._maybe_alert(broken, _Event(), stagnant=False))
    asyncio.run(service._maybe_alert(broken, _Event(), stagnant=False))
    assert len(sent) == 1                      # 同一个问题只报一次

    # 恢复正常 → 重置；再次出问题要能再报
    asyncio.run(service._maybe_alert({"source": "cdp"}, _Event(), stagnant=False))
    asyncio.run(service._maybe_alert(broken, _Event(), stagnant=False))
    assert len(sent) == 2


def test_stagnant_and_error_are_different_conditions(tmp_path):
    sent: list = []
    service = _service(tmp_path, sent)
    asyncio.run(service._maybe_alert({"source": "cdp-error"}, _Event(), stagnant=False))
    asyncio.run(service._maybe_alert({"source": "cdp"}, _Event(), stagnant=True))
    assert len(sent) == 2
    assert "读不到数据" in sent[0][0]
    assert "数据不动" in sent[1][0]


def test_alert_text_tells_you_how_to_fix(tmp_path):
    sent: list = []
    service = _service(tmp_path, sent)
    title, body = service._alert_text(
        "cdp-error", {"room_name": "质润官方旗舰店"}, _Event()
    )
    assert "连接数据源" in body and "恢复盯盘" in body
    assert "质润官方旗舰店" in title
    _, stuck = service._alert_text(
        "stagnant", {"room_name": "质润官方旗舰店", "note": "消耗连续 15 分钟没变"}, _Event()
    )
    assert "刷新数据" in stuck


def test_alert_includes_current_state(tmp_path):
    """告警要带上下文：在哪个直播间、本场几点开播、最后一次成功读数、连失败几轮。"""
    from datetime import UTC, datetime

    sent: list = []
    service = _service(tmp_path, sent)
    service._session_room = "质润官方旗舰店"
    service._session_started_at = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)
    service._last_report_at = datetime(2026, 10, 10, 8, 41, tzinfo=UTC)
    service._consecutive_failures = 3

    _, body = service._alert_text("cdp-error", {}, _Event())
    assert "当前状态：" in body
    assert "质润官方旗舰店" in body
    assert "最后一次成功读数" in body
    assert "已连续失败 3 轮" in body


def test_alert_says_when_never_succeeded(tmp_path):
    sent: list = []
    service = _service(tmp_path, sent)
    _, body = service._alert_text("cdp-error", {}, _Event())
    assert "本进程还没成功读到过数据" in body


# --- 端到端：跑一轮 tick，报表要真的推给前端、异常要真的告警 -------------------

class _Hub:
    def __init__(self):
        self.events = []

    async def publish(self, payload):
        self.events.append(payload)


class _FakeMonitor:
    def __init__(self, event):
        self._event = event

    def tick(self):
        return self._event


def _broken_event():
    from datetime import UTC, datetime

    from app.services.analytics import ComputedMetrics
    from app.services.monitor import MonitorEvent

    return MonitorEvent(
        captured_at=datetime(2026, 10, 10, 8, 0, tzinfo=UTC),
        freshness="stale",
        banner="",
        level="normal",
        reason="CDP page not found for marker: board-next",
        profile_version=1,
        metrics=ComputedMetrics(
            roi=None, gpm=None, spend=0.0, gmv=0.0, orders=0,
            online_viewers=0, views=0,
        ),
        plan_status="active",
        plan_budget=0.0,
        source="cdp-error",
    )


def test_tick_publishes_report_and_alerts_once(tmp_path):
    """回归：曾经因为变量名写错（stagnant / is_stagnant）每轮都抛异常，
    报表推不出去、告警也不发 —— 这条测试就是防止再犯。"""
    sent: list = []
    hub = _Hub()

    async def notifier(title, body):
        sent.append(title)

    service = LiveWatchService(
        _FakeMonitor(_broken_event()),
        hub,
        store=SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json"),
        alert_notifier=notifier,
    )

    report = asyncio.run(service.tick_once())
    assert report.get("source") == "cdp-error"
    # 报表必须推给前端（聊天框靠这个）
    assert [e.get("type") for e in hub.events] == ["live_watch"]
    # 异常要告警
    assert len(sent) == 1

    asyncio.run(service.tick_once())
    assert len(sent) == 1          # 同一个问题不重复刷
    assert len(hub.events) == 2    # 但报表每轮都要推


# --- 自检：读数不动时，要自己去刷新页面再确认 --------------------------------

def _live_event(spend: float):
    from datetime import UTC, datetime

    from app.services.analytics import ComputedMetrics
    from app.services.monitor import MonitorEvent

    return MonitorEvent(
        captured_at=datetime(2026, 10, 10, 8, 0, tzinfo=UTC),
        freshness="fresh",
        banner="",
        level="normal",
        reason="指标正常",
        profile_version=1,
        metrics=ComputedMetrics(
            roi=1.8, gpm=2000.0, spend=spend, gmv=spend * 1.8, orders=10,
            online_viewers=30, views=5000,
        ),
        plan_status="active",
        plan_budget=0.0,
        source="cdp",
        spend_delta=0.0,
        minutes_since_previous=5.0,
    )


class _SameSpendMonitor:
    def __init__(self, spend: float):
        self._spend = spend

    def tick(self):
        return _live_event(self._spend)


def _snapshot_with(spend: float):
    from datetime import UTC, datetime

    from app.execution.cdp.fixture_adapter import MetricSnapshot

    return MetricSnapshot(
        captured_at=datetime(2026, 10, 10, 8, 5, tzinfo=UTC),
        freshness="fresh",
        plan_status="active",
        plan_budget=0.0,
        spend=spend,
        gmv=spend * 1.8,
        orders=10,
        views=5000,
        online_viewers=30,
        roi=1.8,
        gpm=2000.0,
    )


def test_stagnation_auto_refreshes_and_adopts_fresh_value(tmp_path):
    """读数连续不动时，自检要真的去刷页面；刷完有变化就用新值，别误报停滞。"""
    calls = {"n": 0}

    async def refresher():
        calls["n"] += 1
        return _snapshot_with(200.0)

    service = LiveWatchService(
        _SameSpendMonitor(100.0),
        _Hub(),
        store=SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json"),
        snapshot_refresher=refresher,
        state_path=tmp_path / "state.json",
    )
    for _ in range(3):
        report = asyncio.run(service.tick_once())

    assert calls["n"] >= 1                 # 真的去刷新了
    assert report["spend"] == 200.0        # 采用了刷新后的读数
    assert "已自动刷新" in report["report_markdown"] or report["spend"] == 200.0


def test_stagnation_keeps_when_refresh_shows_no_change(tmp_path):
    async def refresher():
        return _snapshot_with(100.0)       # 刷新后还是不动

    service = LiveWatchService(
        _SameSpendMonitor(100.0),
        _Hub(),
        store=SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json"),
        snapshot_refresher=refresher,
        state_path=tmp_path / "state.json",
    )
    for _ in range(3):
        report = asyncio.run(service.tick_once())

    assert report["spend"] == 100.0
    assert "已自动刷新大屏重新读取，数值仍未变化" in report["report_markdown"]
