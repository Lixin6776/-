# -*- coding: utf-8 -*-
"""直播运营助手：对话存储 + 每日汇报。

护栏点（都是这个项目踩过的坑）：
  - 没数据 / 没异常 → 如实写「无」「无异常」，不许硬凑问题；
  - 没校验通过的盯盘数据不能拿来当问题；
  - 汇报只讲「昨天」，不能把今天的数当昨天报；
  - 对话追加不丢历史。
"""

from datetime import date

from app.services.ops_chat import (
    OpsChatStore,
    build_daily_briefing,
    build_ops_context,
)


def _store(tmp_path) -> OpsChatStore:
    return OpsChatStore(tmp_path / "ops_chat.json")


def test_store_appends_and_keeps_order(tmp_path):
    store = _store(tmp_path)
    store.append("user", "今天怎么样", kind="chat")
    store.append("assistant", "先看盯盘", kind="chat")

    items = store.list_messages()
    assert [item["role"] for item in items] == ["user", "assistant"]
    assert items[0]["content"] == "今天怎么样"
    assert store.latest()["content"] == "先看盯盘"


def test_store_detects_today_briefing(tmp_path):
    store = _store(tmp_path)
    assert store.has_today("briefing", "2026-10-09") is False
    store.append("assistant", "汇报", kind="briefing", meta={"day": "2026-10-09"})
    # day 字段由 append 里的当前时间决定，这里显式按记录里的 day 判断
    assert store.has_today("briefing", store.list_messages()[0]["day"]) is True


def test_briefing_without_any_data_says_so():
    text = build_daily_briefing(day=date(2026, 10, 9))
    assert "每日运营汇报｜2026-10-08" in text
    assert "没有可判断的数据" in text
    assert "没有 2026-10-08 的归档复盘" in text
    assert "没有 2026-10-08 的素材分析" in text
    # 不许编出问题
    assert "昨日盯盘没有报出需要处理的问题" in text


def test_briefing_reports_problems_from_watch_reports():
    reports = [
        {
            "created_at": "2026-10-08T20:00:00+08:00",
            "room_name": "质润官方旗舰店",
            "verify_passed": True,
            "problems": ["ROI 未达标：当前 1.80，目标 2.50，缺口 0.70（低 28%）"],
            "adjustments": ["先降追投占比"],
        }
    ]
    text = build_daily_briefing(day=date(2026, 10, 9), watch_reports=reports)
    assert "昨日有 1 类待处理问题" in text
    assert "ROI 未达标" in text
    assert "出现 1 次" in text
    assert "质润官方旗舰店" in text


def test_briefing_ignores_reports_that_failed_verification():
    reports = [
        {
            "created_at": "2026-10-08T20:00:00+08:00",
            "verify_passed": False,
            "problems": ["这条是脏数据，不该出现在汇报里"],
        }
    ]
    text = build_daily_briefing(day=date(2026, 10, 9), watch_reports=reports)
    assert "这条是脏数据" not in text
    assert "无。昨日盯盘没有报出需要处理的问题" in text


def test_briefing_only_covers_yesterday():
    reports = [
        {"created_at": "2026-10-07T20:00:00+08:00", "verify_passed": True,
         "problems": ["前天的问题"]},
        {"created_at": "2026-10-08T20:00:00+08:00", "verify_passed": True,
         "problems": ["昨天的问题"]},
        {"created_at": "2026-10-09T09:00:00+08:00", "verify_passed": True,
         "problems": ["今天的问题"]},
    ]
    text = build_daily_briefing(day=date(2026, 10, 9), watch_reports=reports)
    assert "昨天的问题" in text
    assert "前天的问题" not in text
    assert "今天的问题" not in text


def test_briefing_without_problems_says_no_issue():
    reports = [
        {"created_at": "2026-10-08T20:00:00+08:00", "verify_passed": True, "problems": []}
    ]
    text = build_daily_briefing(day=date(2026, 10, 9), watch_reports=reports)
    assert "昨日未发现需要处理的问题" in text


def test_ops_context_carries_strategy_watch_and_knowledge():
    class _Profile:
        business_direction = "ROI目标 2.7"
        primary_objective = "稳定放量"
        hard_constraints = {"roi_target": 2.7}
        version = 3

    context = build_ops_context(
        profile=_Profile(),
        latest_watch={
            "created_at": "2026-10-09T11:35:00+08:00",
            "room_name": "质润官方旗舰店",
            "roi": 1.77,
            "roi_target": 2.7,
            "spend": 15985.19,
            "problems": ["ROI 未达标"],
            "adjustments": ["先降追投"],
            "verify_passed": True,
        },
        reviews=[{"date": "2026-10-08", "report_markdown": "## 直播复盘" * 400}],
        analyses=[{"date": "2026-10-08", "report_markdown": "## 素材分析"}],
        history=[{"role": "user", "content": "今天怎么样"}],
    )
    assert context["投放策略"]["业务方向"] == "ROI目标 2.7"
    assert context["最新盯盘"]["ROI"] == 1.77
    assert context["最新盯盘"]["目标ROI"] == 2.7
    assert context["最近复盘"][0]["日期"] == "2026-10-08"
    # 长报告要截断，别把上下文撑爆
    assert len(context["最近复盘"][0]["报告"]) <= 2500
    assert context["最近对话"][0]["content"] == "今天怎么样"
    assert context["官方运营手册摘要"]


def test_persona_forbids_fabrication_and_writes():
    from app.services.ops_chat import PERSONA

    assert "不要编造" in PERSONA
    assert "只读" in PERSONA
    assert "没有异常就直说" in PERSONA


def test_briefing_aggregates_repeated_problems_by_type():
    """一次盯盘会反复报同类问题，汇报必须按「类」汇总，不能堆成几百条。"""
    reports = []
    for i in range(140):
        reports.append(
            {
                "created_at": "2026-10-08T20:00:00+08:00",
                "verify_passed": True,
                "problems": [
                    f"ROI 未达标：当前 1.{i % 10}，目标 2.60",
                    f"追投占比严重超标：追投/调控 ¥{9000 + i}（59.7%）",
                    f"承接效率（GPM）比自身基线低 {20 + i % 30}%：当前 ¥2,100",
                ],
            }
        )
    text = build_daily_briefing(day=date(2026, 10, 9), watch_reports=reports)

    assert "3 类待处理问题" in text
    assert "盯盘累计报出 420 次" in text
    assert "出现 140 次" in text
    # 清单里只出现 3 条汇总行，不是 420 条
    body = text.split("### 三、待处理问题清单", 1)[1].split("### 四、", 1)[0]
    numbered = [line for line in body.splitlines() if line.strip().startswith(tuple("123456789"))]
    assert len(numbered) == 3


def test_daily_briefing_replaces_same_day_instead_of_stacking(tmp_path):
    """定时重跑 / 手动补跑 / 开机补跑，同一天只能留一份日报。"""
    store = _store(tmp_path)
    store.append("user", "先问一句")
    first = store.replace_daily_briefing("第一版汇报", day="2026-10-10")
    second = store.replace_daily_briefing("第二版汇报", day="2026-10-10")

    briefings = [m for m in store.list_messages() if m["kind"] == "briefing"]
    assert len(briefings) == 1
    assert briefings[0]["content"] == "第二版汇报"
    assert first["id"] != second["id"]
    # 别人的消息不能被顺手删掉
    assert any(m["content"] == "先问一句" for m in store.list_messages())
    # 不同日期互不影响
    store.replace_daily_briefing("前一天的汇报", day="2026-10-09")
    assert len([m for m in store.list_messages() if m["kind"] == "briefing"]) == 2


def test_concurrent_appends_do_not_lose_messages(tmp_path):
    """并发写入不能互相覆盖。

    真实踩过：盯盘告警和启动补跑复盘同时写，告警被覆盖掉了。
    """
    import threading

    store = _store(tmp_path)
    barrier = threading.Barrier(8)

    def writer(i: int) -> None:
        barrier.wait()
        store.append("assistant", f"消息{i}", kind="chat")

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    contents = {m["content"] for m in store.list_messages(limit=50)}
    assert contents == {f"消息{i}" for i in range(8)}
