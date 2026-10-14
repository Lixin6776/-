# -*- coding: utf-8 -*-
"""复盘补跑。

为什么需要：复盘只在「读到 已结束 的那一次盯盘」触发。如果那一刻电脑/后端没在跑
（关机、重启、崩溃），那一场就永远不会有复盘——10-09 那场就是这么丢的。

这里的策略很保守：**只有当日志里出现了"更新的场次"时，才给旧场次补复盘**。
（新的场次都开播了，旧的必然是结束了，不用猜。）
补出来的复盘会明确标注「补跑生成」，并说明数据来自当天盯盘记录。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.services.analytics import AnalyticsService
from app.services.live_review import build_live_review

BEIJING = ZoneInfo("Asia/Shanghai")


def _session_key(report: dict) -> str:
    """场次标识。

    不能退回 room_name —— 同一个直播间一天好几场，退回名字会把不同场次并成一场；
    更不能给个 "unknown"，那会把同一场切成两组，凭空造出"已结束的旧场次"
    （第一版补跑就是这么把正在直播的 10-10 场补了一份复盘）。
    认不出属于哪一场的记录，直接不要。
    """
    room_id = str(report.get("live_room_id") or "").strip()
    if room_id:
        return f"room:{room_id}"
    started = str(report.get("live_started_at") or "").strip()
    if started:
        return f"start:{started}"
    return ""


def group_sessions(logs: list[dict]) -> list[dict]:
    """把盯盘报表按场次分组（老的在前）。"""
    buckets: dict[str, dict] = {}
    for report in logs:
        if report.get("source") == "cdp-error":
            continue
        key = _session_key(report)
        if not key:
            continue  # 认不出属于哪一场，不参与分组
        bucket = buckets.setdefault(
            key,
            {
                "key": key,
                "room_name": report.get("room_name"),
                "live_started_at": report.get("live_started_at"),
                "reports": [],
            },
        )
        bucket["reports"].append(report)
        if report.get("room_name"):
            bucket["room_name"] = report["room_name"]
        if report.get("live_started_at"):
            bucket["live_started_at"] = report["live_started_at"]
    sessions = list(buckets.values())
    for session in sessions:
        session["reports"].sort(key=lambda r: str(r.get("created_at") or ""))
    sessions.sort(key=lambda s: str(s.get("live_started_at") or ""))
    return sessions


def review_date_of(session: dict) -> str:
    raw = session.get("live_started_at") or (
        session["reports"][-1].get("created_at") if session.get("reports") else None
    )
    try:
        return datetime.fromisoformat(str(raw)).astimezone(BEIJING).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


STALE_MINUTES = 10


def _parse_ts(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=BEIJING)


# 跨天连续长播（马拉松）：时长至少这么长，才按天切；普通场次（哪怕偶尔跨过午夜）不切。
MARATHON_MIN_HOURS = 12


def _day_segments(session: dict) -> list[dict]:
    """把一场「马拉松直播」（跨天 + 时长够长）按北京日期切成"当天段"。

    背景：一场连播 58 小时，按 live_room_id 分场只有一场、日期锚在开播那天，
    中间整整两天的复盘就永远出不来。这里给它按天切段，每个"已经过完的整天"
    各自出一份复盘。

    只有真正跨天的长连播才切；普通的跨午夜短场（比如 23:30 播到次日 02:30）
    不切，保持"一场一份复盘"。切出来的段保留 live_started_at=当天第一条记录时间，
    这样段内日期和报表口径一致。
    """
    reports = session.get("reports") or []
    if not reports:
        return []
    per_day: dict[str, list[dict]] = {}
    for report in reports:
        ts = _parse_ts(report.get("created_at"))
        if ts is None:
            continue
        day = ts.astimezone(BEIJING).strftime("%Y-%m-%d")
        per_day.setdefault(day, []).append(report)
    if len(per_day) < 2:
        return []  # 没有跨天才不切
    first = _parse_ts(reports[0].get("created_at"))
    last = _parse_ts(reports[-1].get("created_at"))
    if first is None or last is None:
        return []
    if (last - first).total_seconds() < MARATHON_MIN_HOURS * 3600:
        return []  # 时长不够，不当作马拉松
    segments: list[dict] = []
    for day in sorted(per_day):
        seg_reports = sorted(per_day[day], key=lambda r: str(r.get("created_at") or ""))
        seg_start = _parse_ts(seg_reports[0].get("created_at"))
        segments.append(
            {
                "key": f"{session.get('key')}#{day}",
                "room_name": session.get("room_name"),
                "live_started_at": seg_start.isoformat() if seg_start else session.get("live_started_at"),
                "reports": seg_reports,
                "date": day,
                "segment_of": session.get("key"),
            }
        )
    return segments


def missing_sessions(
    logs: list[dict],
    existing_dates: set[str],
    now: datetime | None = None,
    allow_latest: bool = False,
) -> list[dict]:
    """找出"已经确定结束、但没有复盘"的场次。

    整场复盘判定要同时满足：
      1. 日志里存在更新的场次（新的都开播了，旧的必然结束）；
      2. 旧场次最后一条记录至少 10 分钟前（避免场次刚切换时的抖动）；
      3. 该日期还没有复盘。

    另外：跨天的**马拉松直播**（时长 ≥ MARATHON_MIN_HOURS）按北京日期切段，
    每个"已经过完的整天"单独补一份复盘——哪怕这场还在播。
    """
    sessions = group_sessions(logs)
    now = now or datetime.now(BEIJING)
    missing: list[dict] = []
    # 整场复盘：要能确认"旧场次已结束"。只有一场、且没有外部确认没在播时，不猜。
    if len(sessions) >= 2 or allow_latest:
        newest_start = (
            _parse_ts(sessions[-1]["reports"][0].get("created_at"))
            if sessions[-1]["reports"]
            else None
        )
        candidates = sessions if allow_latest else sessions[:-1]
        for session in candidates:  # 默认：除最新一场外都已结束；allow_latest=外部已确认没在播
            day = review_date_of(session)
            if not day or day in existing_dates:
                continue
            if not session["reports"]:
                continue
            last_at = _parse_ts(session["reports"][-1].get("created_at"))
            if last_at is None:
                continue
            if (now - last_at).total_seconds() < STALE_MINUTES * 60:
                continue  # 刚结束/可能还在播，这轮不补
            # 与最新场次时间重叠 → 多半是同一场被切开了，宁可不补
            if session is not sessions[-1] and newest_start is not None and last_at >= newest_start:
                continue
            missing.append({**session, "date": day})
    # 马拉松直播：跨天且已过完整天 → 按天补一份复盘（哪怕这场还在播）。
    # 只补「今天之前」的整天，今天的段不补（还没过完，数据不全）。
    today = now.astimezone(BEIJING).strftime("%Y-%m-%d")
    covered = set(existing_dates) | {str(m.get("date")) for m in missing}
    for session in sessions:
        for segment in _day_segments(session):
            day = str(segment.get("date") or "")
            if not day or day >= today:
                continue  # 当天还没过完
            if day in covered:
                continue  # 这天已经有复盘了（整场复盘也算）
            seg_last = _parse_ts(segment["reports"][-1].get("created_at"))
            if seg_last is None:
                continue
            if (now - seg_last).total_seconds() < STALE_MINUTES * 60:
                continue  # 这段刚过，缓一缓
            covered.add(day)
            missing.append(segment)
    missing.sort(key=lambda item: str(item.get("date") or ""))
    return missing


def snapshot_from_report(report: dict, live_started_at=None) -> MetricSnapshot:
    """用盯盘报表里记下来的指标，还原一份快照（缺的字段就留空，不猜）。

    显式传进来的 live_started_at（场次级 / 按天分段的开播时间）优先于单条记录：
    场次最后几条记录可能恰好读不到开播时间（大屏头部不渲染时会这样），
    只信单条记录会把日期算到第二天；按天分段时更要强制用"段"的开播时间。
    """
    return MetricSnapshot(
        captured_at=report.get("created_at"),
        live_started_at=live_started_at or report.get("live_started_at"),
        room_name=report.get("room_name"),
        live_room_id=report.get("live_room_id"),
        freshness="fresh",
        plan_status="ended",
        plan_budget=0.0,
        spend=float(report.get("spend") or 0.0),
        gmv=float(report.get("gmv") or 0.0),
        orders=int(report.get("orders") or 0),
        views=int(report.get("views") or 0),
        online_viewers=int(report.get("online_viewers") or 0),
        roi=report.get("roi"),
        gpm=report.get("gpm"),
        exposure_view_rate=report.get("exposure_view_rate"),
        view_conversion_rate=report.get("view_conversion_rate"),
    )


def build_catch_up_review(session: dict, profile) -> dict:
    """给一场漏掉的直播补一份复盘。"""
    last = session["reports"][-1]
    snapshot = snapshot_from_report(last, live_started_at=session.get("live_started_at"))
    metrics = AnalyticsService().compute(snapshot)
    avg_online = None
    samples = sum(
        1
        for r in session["reports"]
        if isinstance(r.get("online_viewers"), (int, float))
        and float(r.get("online_viewers") or 0) > 0
    )
    if samples >= 3:
        values = [
            float(r["online_viewers"])
            for r in session["reports"]
            if float(r.get("online_viewers") or 0) > 0
        ]
        avg_online = sum(values) / len(values)
    review = build_live_review(
        snapshot,
        metrics,
        profile,
        snapshot.captured_at,
        avg_online=avg_online,
        online_samples=samples,
    )
    if session.get("segment_of"):
        note = (
            f"> ⏱️ **本场复盘只覆盖 {session.get('date')} 这一天（按天分段）**："
            "这是一场跨天的连续直播，中间没有下播，所以按北京日期切成"
            f"当天一段。数据取自该天 {len(session['reports'])} 条盯盘记录"
            f"（截至 {last.get('created_at')}）。"
            "曝光次数 / 观看次数这类只在实时快照里的字段会是空的——缺的就是缺的，没有补猜。\n\n"
        )
    else:
        note = (
            f"> ⏱️ **本场复盘是补跑生成的**：结束那一刻后端没在运行，"
            f"所以没能实时出复盘。数据取自本场 {len(session['reports'])} 条盯盘记录"
            f"（累计到 {last.get('created_at')}），"
            "曝光次数 / 观看次数这类只在实时快照里的字段会是空的——缺的就是缺的，没有补猜。\n\n"
        )
    markdown = str(review.get("report_markdown") or "")
    # 下播那一刻没有数据落库，"结束时间"其实是最后一次读到数据的时间，得说清楚
    markdown = markdown.replace(
        "- 场次：",
        "- 场次（结束时间为「最后一次读到数据」的时间，不是精确下播时间）：",
        1,
    )
    review["report_markdown"] = note + markdown
    # 日期以「场次」为准（开播那天），不看最后一条记录是哪天
    if session.get("date"):
        review["date"] = session["date"]
    review["caught_up"] = True
    review["session_reports"] = len(session["reports"])
    if session.get("segment_of"):
        review["segment_of"] = session.get("segment_of")
        review["segment_date"] = session.get("date")
    return review
