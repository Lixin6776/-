# -*- coding: utf-8 -*-
"""操作净效应：你手动做的操作，有没有被数据正向反馈。

这套口径是先用真实数据做过自检的，不是拍脑袋：

1. 每个「有操作的时刻」，算 **操作前 10 分钟边际 ROI** vs **操作后 10 分钟边际 ROI**；
2. 用「前后 7 分钟都没有任何操作」的时刻当 **对照组**，算出账户的**基线漂移**
   （实测：什么都不做，10 分钟后边际 ROI 也会掉 -0.106 —— 不扣掉它，所有操作都会
   看起来是负的）；
3. **净效应 = 操作组中位Δ − 对照组中位Δ**；
4. 按**流速**分层（慢/中/快）—— 实测不分层会掩盖关键差异
   （慢流速操作 -0.167 / 中 +0.313 / 快 +0.221）；
5. **n<20 只标"样本不足"，不给结论**；结论性质是**观察性相关，不是因果**。
"""

import re
import statistics
from datetime import datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")

MIN_SAMPLE = 20
OP_WINDOW_SECONDS = 7 * 60          # 判定"这一刻附近有操作"的时间窗
FORWARD_MINUTES = 10                # 看操作后 10 分钟
NEIGHBOR_TOLERANCE_SECONDS = 200    # 找 ±10 分钟对照记录时的容差

_OP_TIME = re.compile(r"(\d{2}-\d{2}) (\d{2}:\d{2})")
_OP_TIME_SHORT = re.compile(r"^\s*-?\s*(\d{2}:\d{2}):\d{2}")
_BUDGET = re.compile(r"调控预算[：:]\s*([\d.]+)元\s*->\s*([\d.]+)元")
_LOG_BLOCK = re.compile(r"近 \d+ 分钟有 \d+ 条[：:]\s*\n((?:- .*\n?)+)")


def classify_operation(entry: dict) -> str:
    """把一条平台日志归成可统计的操作类型。认不出的归"其他"，不硬凑。"""
    text = " ".join(
        [str(entry.get("summary") or "")]
        + [str(item) for item in (entry.get("details") or [])]
    )
    kind = str(entry.get("type") or "")
    if "调控状态" in text:
        if "-> 已暂停" in text or "调控手动关闭" in text:
            return "暂停追投"
        if "-> 调控中" in text:
            return "开启追投"
    if "调控预算" in text:
        match = _BUDGET.search(text)
        if match:
            before, after = float(match.group(1)), float(match.group(2))
            if after > before:
                return "加追投预算"
            if after < before:
                return "降追投预算"
            return "预算不变"
        if kind == "新建":
            return "新建追投"
    if "成交出价" in text:
        return "出价调整"
    if "综合营销ROI目标" in text:
        return "ROI目标调整"
    if "增加视频ID" in text or "增加标题ID" in text:
        return "加素材"
    if "删除千川星选" in text:
        return "删素材"
    if "一键起量" in text:
        return "一键起量"
    return "其他"


def _parse_ts(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=BEIJING)


def _ops_from_report(report: dict) -> list[tuple[datetime, str]]:
    """从一条盯盘记录里取出操作。

    新报告直接用结构化的 platform_operations；老报告回退去解析 markdown。
    """
    out: list[tuple[datetime, str]] = []
    for entry in report.get("platform_operations") or []:
        at = _parse_ts(str(entry.get("time") or "").replace(" ", "T"))
        if at is not None:
            out.append((at.astimezone(BEIJING), classify_operation(entry)))
    if out:
        return out

    markdown = str(report.get("report_markdown") or "")
    block = _LOG_BLOCK.search(markdown)
    if not block:
        return []
    report_at = _parse_ts(report.get("created_at"))
    if report_at is None:
        return []
    report_at = report_at.astimezone(BEIJING)
    for line in block.group(1).splitlines():
        text = line.strip()
        if not text:
            continue
        at = None
        match = _OP_TIME.search(text)
        if match:
            try:
                at = datetime.strptime(
                    f"2026-{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=BEIJING)
            except ValueError:
                at = None
        if at is None:
            short = _OP_TIME_SHORT.match(text)
            if short:
                try:
                    at = datetime.strptime(
                        f"2026-{report_at.strftime('%m-%d')} {short.group(1)}",
                        "%Y-%m-%d %H:%M",
                    ).replace(tzinfo=BEIJING)
                except ValueError:
                    at = None
        if at is None:
            continue
        out.append((at, classify_operation({"summary": text, "type": "新建" if "新建" in text[:30] else "修改"})))
    return out


def _marginal_roi(before: dict, after: dict) -> float | None:
    spend_delta = float(after.get("spend") or 0) - float(before.get("spend") or 0)
    gmv_delta = float(after.get("gmv") or 0) - float(before.get("gmv") or 0)
    if spend_delta <= 50:
        return None
    return gmv_delta / spend_delta


def compute_ops_outcome(logs: Iterable[dict]) -> dict:
    """算出《操作反馈表》需要的全部数据。"""
    reports = []
    for report in logs:
        if report.get("source") != "cdp":
            continue
        at = _parse_ts(report.get("created_at"))
        if at is None:
            continue
        reports.append({**report, "_at": at.astimezone(BEIJING)})
    reports.sort(key=lambda item: item["_at"])

    # 去重操作时刻（同一条日志会在多个 tick 里重复出现）
    seen: set[tuple[str, str]] = set()
    op_events: list[tuple[datetime, str]] = []
    for report in reports:
        for at, name in _ops_from_report(report):
            key = (at.isoformat(), name)
            if key in seen:
                continue
            seen.add(key)
            op_events.append((at, name))

    def near(moment: datetime, minutes: int) -> dict | None:
        target = moment + timedelta(minutes=minutes)
        best, best_gap = None, 10**9
        for report in reports:
            gap = abs((report["_at"] - target).total_seconds())
            if gap < best_gap:
                best, best_gap = report, gap
        return best if best_gap <= NEIGHBOR_TOLERANCE_SECONDS else None

    def has_op_near(moment: datetime) -> bool:
        return any(
            abs((moment - op_at).total_seconds()) <= OP_WINDOW_SECONDS
            for op_at, _ in op_events
        )

    rows = []
    for report in reports:
        pre = near(report["_at"], -FORWARD_MINUTES)
        post = near(report["_at"], FORWARD_MINUTES)
        if pre is None or post is None:
            continue
        pre_roi = _marginal_roi(pre, report)
        post_roi = _marginal_roi(report, post)
        if pre_roi is None or post_roi is None:
            continue
        velocity = (float(report.get("spend") or 0) - float(pre.get("spend") or 0)) / 10.0
        rows.append(
            {
                "at": report["_at"],
                "delta": post_roi - pre_roi,
                "velocity": velocity,
                "has_op": has_op_near(report["_at"]),
            }
        )

    control = [row["delta"] for row in rows if not row["has_op"]]
    treated = [row["delta"] for row in rows if row["has_op"]]
    baseline = statistics.median(control) if control else 0.0

    def summarize(values: list[float]) -> dict:
        if not values:
            return {"n": 0, "median_delta": None, "positive_rate": None, "net_effect": None}
        median = statistics.median(values)
        return {
            "n": len(values),
            "median_delta": round(median, 4),
            "positive_rate": round(sum(1 for v in values if v > 0) / len(values), 4),
            "net_effect": round(median - baseline, 4),
        }

    # 按操作类型汇总：以"时刻"为单位归属（同一时刻有多个操作就各记一次），
    # 不能每个操作各抓一条 —— 那样会重复计数、且数字随解析顺序漂移。
    by_type: dict[str, list[float]] = {}
    for row in rows:
        if not row["has_op"]:
            continue
        names = {
            name
            for at, name in op_events
            if abs((row["at"] - at).total_seconds()) <= OP_WINDOW_SECONDS
        }
        # 只统计"此刻只有一种操作"的样本：操作扎堆时无法区分是哪一个起的作用，
        # 硬算会让所有操作类型都继承同一个效应（实测会全部变成 positive）。
        if len(names) != 1:
            continue
        by_type.setdefault(next(iter(names)), []).append(row["delta"])

    operations = []
    for name, values in sorted(by_type.items(), key=lambda kv: len(kv[1]), reverse=True):
        summary = summarize(values)
        summary["operation"] = name
        summary["verdict"] = (
            "insufficient"
            if summary["n"] < MIN_SAMPLE
            else ("positive" if (summary["net_effect"] or 0) > 0.1 else "negative" if (summary["net_effect"] or 0) < -0.1 else "neutral")
        )
        operations.append(summary)

    # 按流速分层（这是实测里最有价值的切法）
    velocities = sorted(row["velocity"] for row in rows)
    strata = []
    if len(velocities) >= 6:
        low, high = statistics.quantiles(velocities, n=3)[0], statistics.quantiles(velocities, n=3)[1]
        for label, predicate in (
            ("慢", lambda v: v < low),
            ("中", lambda v: low <= v < high),
            ("快", lambda v: v >= high),
        ):
            treated_v = [row["delta"] for row in rows if row["has_op"] and predicate(row["velocity"])]
            control_v = [row["delta"] for row in rows if not row["has_op"] and predicate(row["velocity"])]
            item = {
                "label": label,
                "treated": summarize(treated_v),
                "control": summarize(control_v),
            }
            if item["treated"]["n"] and item["control"]["n"]:
                item["net_effect"] = round(
                    item["treated"]["median_delta"] - item["control"]["median_delta"], 4
                )
                item["verdict"] = (
                    "insufficient"
                    if min(item["treated"]["n"], item["control"]["n"]) < MIN_SAMPLE
                    else ("positive" if item["net_effect"] > 0.1 else "negative" if item["net_effect"] < -0.1 else "neutral")
                )
            else:
                item["net_effect"] = None
                item["verdict"] = "insufficient"
            strata.append(item)

    return {
        "generated_at": datetime.now(BEIJING).isoformat(),
        "window_minutes": FORWARD_MINUTES,
        "min_sample": MIN_SAMPLE,
        "baseline": summarize(control) | {"operation": "（基线：无操作时刻）"},
        "treated": summarize(treated),
        "operations": operations,
        "velocity_strata": strata,
        "note": "观察性相关，不是因果：操作是你自己按状态选的，且同一时刻可能有多个操作。",
    }
