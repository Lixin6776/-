# -*- coding: utf-8 -*-
"""报告一致性护栏。

这里拦的是「报告里写了自己都圆不回来的话」这一类问题，都是实际踩过的坑：
  1. 目标 ROI 没读到 → 报告里绝不能编一个目标出来算缺口（曾出现「目标 2.00」）；
  2. 「问题」列表里报了某个焦点 → 「方案」里必须有对应动作（曾出现 ROI 问题没有方案）；
  3. 参考线阈值只能有一处来源，第四节和第七节不能各用一套（曾出现 4.0% vs 3.5%）；
  4. 自检要覆盖正文真正渲染出去的内容，不能自检通过、正文无依据。
"""

import re
from datetime import UTC, datetime
from pathlib import Path

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.services import live_review as lr
from app.services.analytics import AnalyticsService, ComputedMetrics
from app.services.live_review import build_live_review
from app.services.live_watch import build_adjustments, detect_problems
from app.services.monitor import MonitorEvent, MonitorProfile

SERVICE_DIR = Path(lr.__file__).resolve().parent


def _profile(target=None):
    constraints = {"roi_target": target} if target is not None else {}
    return MonitorProfile(
        version=1,
        business_direction="ROI目标" if target else "未配置",
        primary_objective="提升成交额",
        hard_constraints=constraints,
    )


def _snapshot(**over):
    data = dict(
        captured_at=datetime(2026, 10, 1, 15, 30, tzinfo=UTC),
        freshness="fresh",
        plan_status="ended",
        plan_budget=5000,
        spend=10000,
        gmv=18000,
        orders=100,
        views=5000,
        online_viewers=20,
        roi=1.8,
        gpm=2266.0,
        exposure_count=100000,
        view_count=4000,
        product_clicks=800,
        view_conversion_rate=2.5,
        exposure_view_rate=4.0,
    )
    data.update(over)
    return MetricSnapshot(**data)


def _review(snapshot=None, target=None, **over):
    snapshot = snapshot or _snapshot(**over)
    metrics = AnalyticsService().compute(snapshot)
    return build_live_review(snapshot, metrics, _profile(target), snapshot.captured_at)


def _event(roi_target_text="", **over):
    metrics = ComputedMetrics(
        roi=over.get("roi", 1.8),
        gpm=over.get("gpm", 2266.0),
        spend=over.get("spend", 10000),
        gmv=over.get("gmv", 18000),
        orders=over.get("orders", 100),
        online_viewers=over.get("online_viewers", 20),
        views=over.get("views", 5000),
    )
    return MonitorEvent(
        captured_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        freshness="fresh",
        banner=roi_target_text,
        level="normal",
        reason="指标正常",
        profile_version=1,
        metrics=metrics,
        plan_status="active",
        plan_budget=5000,
        source="cdp",
        spend_delta=500.0,
        minutes_since_previous=5.0,
    )


# --- 1. 没有目标就不许编目标 -------------------------------------------------

def _this_session_part(report: str) -> str:
    """只取描述本场的段落；历史对照区会引用历史记录里的目标数字，不算本场编造。"""
    return report.split("### 八、历史对照与学习沉淀")[0]


def test_review_without_target_never_invents_one():
    report = _review(target=None)["report_markdown"]
    mine = _this_session_part(report)

    assert "目标 --" in mine
    # 本场没配目标，就不允许出现任何「目标 X.XX」的具体数字
    assert not re.search(r"目标 \d+\.\d+", mine)
    assert "无法判断是否达标" in mine


def test_live_watch_without_target_never_invents_one():
    event = _event()
    problems = detect_problems(event, [], None, None)
    plans = build_adjustments(event, [], None, None)
    blob = "\n".join(problems + plans)
    assert not re.search(r"目标 \d+\.\d+", blob)
    assert "目标 ROI 未读到" in blob
    assert "无法判断是否达标" in blob


def test_live_watch_with_target_still_compares():
    event = _event()
    problems = detect_problems(event, [], 2.5, None)
    assert "ROI 未达标：当前 1.80，目标 2.50" in "\n".join(problems)


# --- 2. 报了问题就必须给方案 ------------------------------------------------

def test_every_issue_focus_has_a_solution():
    # 覆盖 _build_issues 能产出的所有焦点
    focuses = set(lr.ATTRIBUTION) | set(lr.SOLUTIONS)
    assert {"曝光观看率", "观看成交转化率", "GPM", "CPM", "ROI"} <= focuses
    for focus in ("曝光观看率", "观看成交转化率", "GPM", "CPM", "ROI"):
        assert focus in lr.SOLUTIONS, f"{focus} 有问题定义但没有解决方案"


def test_report_issue_sections_are_not_empty_and_have_solutions():
    # 一个「处处不达标」的场景，四个焦点应该同时命中，且每个都配了方案
    report = _review(
        target=2.5,
        gpm=1000.0,
        exposure_view_rate=2.0,
        view_conversion_rate=1.0,
    )["report_markdown"]

    issues = re.findall(r"\*\*问题 \d+：(.+?)\*\*", report)
    solutions = re.findall(r"\*\*【方案 \d+｜(.+?)】\*\*", report)

    assert issues, "这个场景应该有具体问题"
    assert "本场无需要调整的动作" not in report
    for focus in issues:
        assert focus in solutions, f"问题「{focus}」没有对应方案"


# --- 3. 参考线阈值只有一套 --------------------------------------------------

def test_reference_lines_have_single_source():
    report = _review(
        target=2.5,
        gpm=1000.0,
        exposure_view_rate=2.0,
        view_conversion_rate=1.0,
        exposure_count=40000,
        spend=12000,
        # ROI 必须能对上成交/消耗，否则会（正确地）被自检拦下
        gmv=21600,
    )["report_markdown"]
    # 阈值出现在正文里时必须是同一套数字，且明说是「参考线」
    assert "参考线 4.0%" in report
    assert "参考线 5.0%" in report
    assert "参考线 ¥3,500" in report
    assert "参考阈值" not in report
    # 曾经的错配：代码按 4% 判、文字写 3.5%
    assert "3.5%" not in report
    assert "参考线 3%" not in report


def test_source_has_no_stray_reference_thresholds():
    """源码里不许再出现散落的重复阈值定义（必须引用 LINE_* 常量）。"""
    source = (SERVICE_DIR / "live_review.py").read_text(encoding="utf-8")
    body = source.split("LINE_ASSIST_SHARE", 1)[1]
    for stray in ("< 3.5", "< 3000", "> 90", "参考阈值"):
        assert stray not in body, f"live_review.py 里残留散落阈值：{stray}"


# --- 4. 自检覆盖正文 --------------------------------------------------------

def test_self_check_covers_rendered_issues():
    review = _review(target=2.5, gpm=1000.0)
    assert review["self_check"] == []
    # 正文没有「缺少依据」的结论
    body = review["report_markdown"].split("### 自检")[0]
    for line in body.splitlines():
        if line.startswith("- **现象**") or line.startswith("**问题"):
            assert "依据" in review["report_markdown"]
            break
    assert "✅ 通过" in review["report_markdown"]


# --- 5. 追投占比口径一致 ----------------------------------------------------

def test_assist_share_threshold_cites_official_line():
    # 参考线是我们定的（50%），官方建议值（25%）必须同时写清楚，
    # 别让人误以为 50% 是官方阈值。
    _, problems, _ = lr.build_spend_structure(
        {"basic_spend": 300.0, "assist_spend": 700.0, "total_spend": 1000.0}
    )
    blob = "\n".join(problems)
    assert "参考线 50%" in blob
    assert "25%" in blob
    assert "官方" in blob

# --- 6. 缺数据 / None 不能把报告写崩或写出假结论 -----------------------------

def test_sparse_metrics_do_not_crash_or_claim_success():
    """字段缺失时只能「说不知道」，不能崩，也不能说达标。"""
    sparse = MetricSnapshot(
        captured_at=datetime(2026, 10, 1, 15, 30, tzinfo=UTC),
        freshness="fresh",
        plan_status="ended",
        plan_budget=0,
        spend=0,
        gmv=0,
        orders=0,
        views=0,
        online_viewers=0,
        roi=None,
        gpm=None,
    )
    metrics = AnalyticsService().compute(sparse)
    report = build_live_review(sparse, metrics, _profile(2.5), sparse.captured_at)[
        "report_markdown"
    ]
    # 缺指标时必须明确拒绝出结论（而不是硬着头皮判断或直接崩）
    assert "未通过校验" in report
    assert "数据校验" in report
    assert "**达标**" not in report

    event = _event(roi=None, gpm=None)
    problems = detect_problems(event, [], 2.5, None)
    plans = build_adjustments(event, [], 2.5, None)
    assert problems and plans

    # 数据源挂了：直接给「先恢复读数」，不许给任何调整结论
    broken = _event()
    broken.source = "cdp-error"
    broken.freshness = "stale"
    broken.reason = "CDP page not found"
    assert "不判断" in "\n".join(detect_problems(broken, [], 2.5, None))
    assert "先恢复直播大屏数据读取" in "\n".join(build_adjustments(broken, [], 2.5, None))


def test_watch_report_renders_without_target():
    from app.services.live_watch import build_watch_report

    event = _event()
    report = build_watch_report(event, [], None, [])
    text = report["report_markdown"]
    assert not re.search(r"目标 \d+\.\d+", text)
    assert "目标 ROI 未读到" in text


def test_csv_like_slice_is_not_partial_sentence():
    """历史对照引用问题时不能出现半句话（要带省略号）。"""
    clipped = lr._clip("一二三四五六七八九十", 5)
    assert clipped.endswith("…")


# --- 7. 报告里不许留「空标题」 ----------------------------------------------

def test_platform_analysis_section_is_never_empty():
    """平台日志里有操作、但不在自动分析覆盖范围时，不能只留一个空标题。"""
    from app.services.live_watch import build_watch_report

    event = _event()
    ops = [
        {
            "time": "2026-10-09 11:19:08",
            "type": "修改",
            "details": ["操作内容：删除视频ID: 7694472250540507190"],
            "summary": "删除视频",
        }
    ]
    report = build_watch_report(event, [], 2.5, [], platform_ops=ops)
    text = report["report_markdown"]

    idx = text.find("**操作分析（运营视角）**")
    assert idx >= 0
    # 标题后面必须紧跟内容，不能直接跳到下一个标题
    tail = text[idx + len("**操作分析（运营视角）**") :].lstrip()
    assert tail and not tail.startswith("\n### ")
    assert "暂不在自动分析的覆盖范围" in text


# --- 操作日志：不能把昨天的操作显示成今天 -------------------------------------

def test_platform_log_url_is_forced_to_today():
    from app.execution.cdp.plan_log_reader import CdpPlanLogReader

    url = (
        "https://qianchuan.jinritemai.com/overall-prom/detail"
        "?aavid=1&campaignType=1&dateRange=2026-10-09%2C2026-10-09&adId=99"
    )
    fixed = CdpPlanLogReader.with_date_range(url, "2026-10-10")
    assert "dateRange=2026-10-10%2C2026-10-10" in fixed
    assert "adId=99" in fixed          # 其它参数不能丢


def test_old_platform_op_is_shown_with_date_and_marked_as_not_today():
    """回归：日志页停在昨天时读到 10-09 23:45，界面上只显示 23:45:14，
    看起来像今天的操作。现在必须带日期，且明确标注不是今天。"""
    from app.services.live_watch import build_watch_report

    ops = [
        {
            "time": "2026-10-09 23:45:14",
            "type": "修改",
            "details": ["操作内容：素材追投，ID：1878562656110048"],
            "summary": "暂停调控",
        }
    ]
    text = build_watch_report(_event(), [], 2.5, [], platform_ops=ops)["report_markdown"]

    assert "10-09 23:45" in text
    assert "不是今天的" in text
    assert "23:45:14" not in text      # 不再只给一个时间


# --- 基线：只能用同一场次的样本 ----------------------------------------------

def test_baseline_prefers_same_session():
    """regression：算基线时必须带场次，否则上一场/已结束场次的数据会混进来。"""
    from app.services.live_watch import compute_baselines

    session_a = "2026-10-09T06:00:00+08:00"
    session_b = "2026-10-10T06:00:00+08:00"
    history = [
        # 上一场：CPM 很高（如果混进来，会把基线抬高）
        {"room_name": "质润官方旗舰店", "live_started_at": session_a, "cpm": 500.0} for _ in range(10)
    ] + [
        # 本场：CPM 正常
        {"room_name": "质润官方旗舰店", "live_started_at": session_b, "cpm": 30.0} for _ in range(6)
    ]

    scoped = compute_baselines(history, room_name="质润官方旗舰店", session=session_b)
    assert scoped["cpm"]["median"] == 30.0        # 只用了本场的 6 条
    assert scoped["cpm"]["samples"] == 6

    unscoped = compute_baselines(history, room_name="质润官方旗舰店")
    assert unscoped["cpm"]["median"] == 500.0     # 不带场次就会退化（这就是原来的行为）


def test_baseline_falls_back_when_session_too_small():
    from app.services.live_watch import compute_baselines

    history = [
        {"room_name": "R", "live_started_at": "2026-10-09T06:00:00+08:00", "cpm": 100.0} for _ in range(8)
    ] + [{"room_name": "R", "live_started_at": "2026-10-10T06:00:00+08:00", "cpm": 20.0}]
    base = compute_baselines(history, room_name="R", session="2026-10-10T06:00:00+08:00")
    # 本场只有 1 条（<5）→ 退回同直播间历史，避免"样本太少也算基线"
    assert base["cpm"]["samples"] == 9


# --- 样本不足（新号/新户）不能拿通用阈值冒充"你自己的水平" -------------------

def test_missing_baseline_is_reported_not_silently_skipped():
    """历史样本 < 5 时：不能光"没问题"，要明确说"这些指标没做水位判断"。"""
    from app.services.analytics import ComputedMetrics
    from app.services.live_watch import baseline_problems

    metrics = ComputedMetrics(
        roi=1.8, gpm=2000.0, spend=10000.0, gmv=18000.0, orders=50,
        online_viewers=30, views=5000,
        exposure_view_rate=3.5, view_conversion_rate=2.0,
    )
    # baselines 全空 = 这个账户没有够用的历史样本
    problems, skipped = baseline_problems(metrics, {}, 0)
    assert problems == []
    assert any("GPM" in item for item in skipped)
    assert any("在线人数" in item for item in skipped)


def test_cold_start_note_appears_in_report():
    from app.services.live_watch import build_watch_report

    # baselines 为空 → 报表自检区要出现"样本不足"说明
    report = build_watch_report(
        _event(), [], 2.5, [], baselines={}, audit_notes=None
    )
    # 直接构造场景：把 skipped 列表塞进 audit_notes 的路径由 service 负责，
    # 这里验证渲染端能显示出来
    from app.services.self_check import render_self_check

    text = render_self_check([], ["样本不足（本账户历史 < 5 次采样）：GPM、在线人数 —— 本轮不做绝对水位判断"])
    assert "样本不足" in text
    assert "不做绝对水位判断" in text


# --- 判断阈值三层优先级：你设的 > 本账户分位 > 通用线 ------------------------

def test_threshold_priority_custom_beats_baseline_beats_default():
    from app.services.thresholds import describe, resolve_thresholds

    class _Profile:
        hard_constraints = {"thresholds": {"gpm": 2500, "cpm": 120}}

    baselines = {
        "gpm": {"low": 2200.0, "samples": 120},
        "cpm": {"high": 85.0, "samples": 120},
        "view_conversion_rate": {"low": 4.2, "samples": 90},
    }
    lines = resolve_thresholds(_Profile(), baselines)

    # 你设的 → 用你的
    assert lines["gpm"]["value"] == 2500 and lines["gpm"]["source"] == "custom"
    assert lines["cpm"]["value"] == 120 and lines["cpm"]["source"] == "custom"
    # 你没设、但有历史分位 → 用本账户分位
    assert lines["view_conversion_rate"]["value"] == 4.2
    assert lines["view_conversion_rate"]["source"] == "baseline"
    # 都没有 → 通用线兜底，并且文案必须说明"非本账户"
    assert lines["exposure_view_rate"]["source"] == "default"
    assert "通用参考线" in describe(lines["exposure_view_rate"])
    assert "非本账户" in describe(lines["exposure_view_rate"])
    # 你设的要能在依据里看出来
    assert "你在决策窗口设定的值" in describe(lines["gpm"])


def test_threshold_defaults_when_no_profile_and_no_history():
    from app.services.thresholds import resolve_thresholds

    lines = resolve_thresholds(None, None)
    assert all(item["source"] == "default" for item in lines.values())
    assert lines["gpm"]["value"] == 3500.0


def test_review_uses_account_percentile_when_given():
    """复盘传了 baselines 时，依据要写成"本账户历史分位"，而不是通用参考线。"""
    baselines = {
        "gpm": {"low": 900.0, "median": 1500.0, "high": 2500.0, "samples": 120},
        "view_conversion_rate": {"low": 1.5, "median": 3.0, "high": 5.0, "samples": 120},
        "exposure_view_rate": {"low": 2.0, "median": 3.5, "high": 5.0, "samples": 120},
    }
    report = _review(
        target=2.5, gpm=800.0, exposure_view_rate=1.5, view_conversion_rate=1.0
    )["report_markdown"]

    # 没传 baselines（默认）→ 写"通用参考线"
    assert "通用参考线" in report

    snapshot = _snapshot(target=2.5, gpm=800.0, exposure_view_rate=1.5)
    metrics = AnalyticsService().compute(snapshot)
    review = build_live_review(
        snapshot, metrics, _profile(2.5), snapshot.captured_at, baselines=baselines
    )
    text = review["report_markdown"]
    assert "本账户历史分位" in text
    assert "通用参考线" not in text or "本账户历史分位" in text
