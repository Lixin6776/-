# -*- coding: utf-8 -*-
"""直播盯盘：每 N 分钟输出一次数据报表 + 问题 + 调整方案，并记录操作日志。"""

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.services.monitor import MonitorEvent
from app.services.watch_log_store import SqliteWatchLogStore
from app.services.diagnosis import diagnose
from app.services.self_check import render_self_check, self_check, verify_data

BEIJING = ZoneInfo("Asia/Shanghai")
LIVE_WATCH_PATH = Path(__file__).resolve().parents[3] / ".local" / "live_watch_logs.json"
LIVE_WATCH_STATE_PATH = (
    Path(__file__).resolve().parents[3] / ".local" / "live_watch_state.json"
)


def _money(value: float | None) -> str:
    return "--" if value is None else f"¥{value:,.2f}"


def _ratio(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}"


def _fmt_int(value) -> str:
    if value is None:
        return "--"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "--"


def _delta(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:+,.2f}"


class LiveWatchLogStore:
    def __init__(self, path: Path = LIVE_WATCH_PATH) -> None:
        self.path = path

    def list_logs(self, limit: int = 50) -> list[dict]:
        items = self._read()
        return list(reversed(items))[:limit]

    def latest(self) -> dict | None:
        items = self._read()
        return items[-1] if items else None

    def append(self, report: dict) -> dict:
        items = self._read()
        items.append(report)
        self._write(items[-500:])
        return report

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def _write(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _recent_operations(limit: int = 5) -> list[dict]:
    """最近的真实执行记录（操作日志）。"""
    try:
        from app.db import SessionLocal
        from app.models import ExecutionJob
    except Exception:  # noqa: BLE001
        return []
    try:
        with SessionLocal() as session:
            jobs = list(
                session.scalars(
                    select(ExecutionJob).order_by(ExecutionJob.created_at.desc()).limit(limit)
                )
            )
    except Exception:  # noqa: BLE001
        return []
    def _summarize(result: dict) -> str:
        """把一次操作的前后差异压成一句中文，便于复盘。"""
        before = (result or {}).get("before") or {}
        after = (result or {}).get("after") or {}
        labels = {
            "budget": "预算",
            "bid": "出价",
            "roi_goal": "ROI目标",
            "status": "状态",
            "name": "计划名",
            "targeting": "定向",
            "schedule": "投放时段",
        }
        status_text = {
            "active": "投放中",
            "paused": "已暂停",
            "reviewing": "审核中",
            "deleted": "已删除",
            "ended": "投放结束",
        }
        money_fields = {"budget", "bid"}
        parts = []
        for key, label in labels.items():
            if key not in before and key not in after:
                continue
            old_value = before.get(key)
            new_value = after.get(key)
            if old_value == new_value:
                continue
            if key == "status":
                old_text = status_text.get(str(old_value), str(old_value))
                new_text = status_text.get(str(new_value), str(new_value))
            elif key in money_fields:
                def fmt(value):
                    try:
                        return f"¥{float(value):,.2f}"
                    except (TypeError, ValueError):
                        return str(value)
                old_text, new_text = fmt(old_value), fmt(new_value)
            else:
                old_text, new_text = str(old_value), str(new_value)
            parts.append(f"{label} {old_text} → {new_text}")
        return "；".join(parts[:3]) or "已执行"

    return [
        {
            "job_id": job.id,
            "action_name": job.action_name,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else "",
            "summary": _summarize(job.result or {}),
            "result": job.result or {},
        }
        for job in jobs
    ]


def _cpm(metrics) -> float | None:
    """千次曝光成本。曝光次数必须 ≥ 观看次数，否则说明数据有问题，不计算。"""
    exposure = getattr(metrics, "exposure_count", None) or 0
    spend = getattr(metrics, "spend", 0) or 0
    views = getattr(metrics, "view_count", None) or 0
    if exposure <= 0 or spend <= 0:
        return None
    if views and exposure < views:
        return None  # 曝光比观看还少，数据不成立
    cpm = spend / (exposure / 1000)
    # 合理性上限：直播全域 CPM 正常在几十到几百元
    if cpm > 5000:
        return None
    return cpm


BASELINE_METRICS = {
    "cpm": "CPM",
    "gpm": "GPM",
    "exposure_view_rate": "曝光观看率",
    "online_viewers": "在线人数",
    "view_conversion_rate": "观看成交转化率",
}


def compute_baselines(
    history: list[dict],
    room_name: str | None = None,
    session: str | None = None,
) -> dict:
    """用账户自己的历史中位数当基准。

    优先只用「同一场次」的样本（场次内累计值才可比）；
    场次内样本不足时，才退回同直播间的历史样本。
    """
    same_room = [
        item
        for item in history
        if (room_name is None or item.get("room_name") == room_name)
    ]
    pool = [i for i in same_room if session and i.get("live_started_at") == session]
    if len(pool) < 5:
        pool = same_room
    if len(pool) < 5:
        pool = history
    result: dict[str, dict] = {}
    for key in BASELINE_METRICS:
        values = []
        for item in pool[-400:]:
            value = item.get(key)
            try:
                if value is not None:
                    values.append(float(value))
            except (TypeError, ValueError):
                continue
        if len(values) >= 5:
            values.sort()
            result[key] = {
                "median": values[len(values) // 2],
                "samples": len(values),
                "low": values[int(len(values) * 0.1)],
                "high": values[int(len(values) * 0.9)],
            }
    return result


def deviation_pct(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return (float(current) - float(base)) / float(base) * 100


def baseline_problems(
    metrics, baselines: dict, history_len: int
) -> tuple[list[str], list[str]]:
    """跟自己的历史比：偏离基线一定程度才算问题，依据自带。

    返回 (问题列表, 样本不足没做判断的指标列表)。

    第二条很关键：样本不足时以前是**静默跳过**的，用户分不清"没问题"和
    "没基准可比"。新号/新户期必须显式说明——不能拿通用阈值冒充"你自己的水平"。
    """
    problems: list[str] = []
    skipped: list[str] = []
    cpm_now = _cpm(metrics)
    checks = [
        ("cpm", cpm_now, "high", 20, "流量成本（CPM）比自身基线高"),
        ("gpm", metrics.gpm, "low", 15, "承接效率（GPM）比自身基线低"),
        ("exposure_view_rate", getattr(metrics, "exposure_view_rate", None), "low", 15,
         "素材/画面吸引力（曝光观看率）比自身基线低"),
        ("online_viewers", metrics.online_viewers, "low", 30, "在线人数比自身基线低"),
        ("view_conversion_rate", getattr(metrics, "view_conversion_rate", None), "low", 20,
         "观看成交转化率比自身基线低"),
    ]
    for key, current, direction, threshold, label in checks:
        base_info = baselines.get(key)
        if not base_info:
            if current is not None:
                skipped.append(label)
            continue
        base = base_info["median"]
        dev = deviation_pct(current, base)
        if dev is None:
            continue
        if direction == "high" and dev >= threshold:
            problems.append(
                f"{label} {dev:.0f}%：当前 {_fmt_metric(key, current)}，"
                f"近 {base_info['samples']} 次盯盘中位 {_fmt_metric(key, base)}"
                f"（依据：比自身基线高 {dev:.0f}% > 阈值 {threshold}%）"
            )
        elif direction == "low" and dev <= -threshold:
            problems.append(
                f"{label} {abs(dev):.0f}%：当前 {_fmt_metric(key, current)}，"
                f"近 {base_info['samples']} 次盯盘中位 {_fmt_metric(key, base)}"
                f"（依据：比自身基线低 {abs(dev):.0f}% > 阈值 {threshold}%）"
            )
    return problems, skipped


def _fmt_metric(key: str, value) -> str:
    if value is None:
        return "--"
    if key in ("cpm", "gpm"):
        return f"¥{float(value):,.2f}"
    if key == "exposure_view_rate":
        return f"{float(value):.2f}%"
    return f"{float(value):.0f}"


def _short(value: str, limit: int = 22) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def spend_split_ratio(split: dict | None) -> float | None:
    """追投/调控消耗占比（%）。"""
    if not split:
        return None
    basic = split.get("basic_spend")
    assist = split.get("assist_spend")
    try:
        basic = float(basic or 0)
        assist = float(assist or 0)
    except (TypeError, ValueError):
        return None
    total = basic + assist
    if total <= 0:
        return None
    return assist / total * 100


POOR_MATERIAL_SPEND = 500.0
POOR_MATERIAL_RATIO = 0.8


def _pick_materials(
    split: dict | None,
    roi_target: float | None,
    account_roi: float | None = None,
) -> tuple[dict | None, list[dict]]:
    """挑出「高消耗低效」和「高 ROI」的素材。

    低效判定：消耗 > ¥500 且 ROI < 账户实际 ROI × 0.8
    （跟账户自己的实际水平比，而不是跟目标比）
    """
    if not split:
        return None, []
    materials = [m for m in (split.get("materials") or []) if (m.get("spend") or 0) > 0]
    if not materials:
        return None, []

    # 只拿「账户实际 ROI」或「目标 ROI」当基准；两个都没有就不判素材好坏，
    # 绝不能自己编一个 2.0 出来（会把正常素材误判成低效）
    reference = account_roi if account_roi is not None else roi_target
    if reference is None:
        return None, []
    cutoff = reference * POOR_MATERIAL_RATIO
    poor = [
        m
        for m in materials
        if (m.get("roi") is None or float(m.get("roi")) < cutoff)
        and float(m.get("spend") or 0) > POOR_MATERIAL_SPEND
    ]
    poor.sort(key=lambda m: float(m.get("spend") or 0), reverse=True)

    best_threshold = roi_target if roi_target is not None else reference
    best = [
        m
        for m in materials
        if m.get("roi") is not None and float(m.get("roi")) >= best_threshold
    ]
    best.sort(key=lambda m: float(m.get("roi") or 0), reverse=True)
    return (poor[0] if poor else None), best[:2]


def detect_problems(
    event: MonitorEvent,
    history: list[dict],
    roi_target: float | None,
    split: dict | None = None,
) -> list[str]:
    """按「整体 → 消耗 → 素材」逐层定位，给出带数字的具体问题。"""
    metrics = event.metrics
    problems: list[str] = []
    # 目标 ROI 没读到就是没读到，不能编一个默认值出来当目标
    threshold = roi_target
    target_known = threshold is not None

    if event.source == "cdp-error" or event.freshness != "fresh":
        return [f"数据读取异常：{event.reason or '直播大屏未刷新'}，本轮不判断"]

    # 1) 整体 ROI
    roi_ok = bool(target_known and metrics.roi is not None and metrics.roi >= threshold)
    if metrics.roi is not None and not target_known:
        problems.append(
            f"目标 ROI 未读到：当前整体 ROI {metrics.roi:.2f}，本轮无法判断是否达标"
            "（先确认该直播间计划里的综合营销 ROI 目标）"
        )
    elif target_known and metrics.roi is not None and metrics.roi < threshold:
        gap = threshold - metrics.roi
        pct = gap / threshold * 100 if threshold else 0
        problems.append(
            f"ROI 未达标：当前 {metrics.roi:.2f}，目标 {threshold:.2f}，"
            f"缺口 {gap:.2f}（低 {pct:.0f}%）"
        )

    # 2) 消耗节奏
    window = event.minutes_since_previous
    window_text = f"近 {window:.0f} 分钟" if window else "本周期"
    if event.spend_delta is not None:
        enough_window = window is None or window >= 3
        if abs(event.spend_delta) < 1 and enough_window:
            problems.append(
                f"消耗停滞：{window_text}仅增加 {_money(event.spend_delta)}，"
                "要区分是预算撞线、计划被限流，还是素材跑不动"
            )
        elif metrics.spend > 0 and event.spend_delta > max(300.0, metrics.spend * 0.05):
            problems.append(
                f"消耗突然加快：{window_text}增加 {_money(event.spend_delta)}，"
                "先定位是哪条计划在放量"
            )

    # 3) 追投占比
    ratio = spend_split_ratio(split)
    if ratio is not None and split is not None:
        basic = float(split.get("basic_spend") or 0)
        assist = float(split.get("assist_spend") or 0)
        if ratio > 50:
            problems.append(
                f"追投占比偏高：追投/调控 {_money(assist)}（{ratio:.1f}%），"
                f"基础计划仅 {_money(basic)}"
                "（分母口径：**素材口径消耗**，不是账户总消耗）"
                "（依据：官方《素材追投调控产品手册》建议控成本追投占账户总消耗约 25%，"
                "官方原文明确『调控量级太大会和主计划抢量，且会拉低总体账户 roi』；"
                "注意这是账户口径的建议值，和上面的素材口径占比不能直接等号对比，"
                "只作为「结构偏重」的方向参考）"
            )
        elif ratio > 25:
            problems.append(
                f"追投占比高于官方建议：追投/调控 {_money(assist)}（{ratio:.1f}%，"
                "分母为素材口径消耗）"
                "（依据：官方建议控成本追投占账户总消耗 **25% 左右**）"
            )

    # 4) 素材层面
    poor, _ = _pick_materials(split, threshold, account_roi=metrics.roi)
    if poor is not None:
        total = float((split or {}).get("total_spend") or 0)
        share = float(poor.get("spend") or 0) / total * 100 if total else 0
        roi_text = f"{float(poor['roi']):.2f}" if poor.get("roi") is not None else "无"
        base_roi = metrics.roi if metrics.roi is not None else threshold
        cutoff = (base_roi or 0.0) * POOR_MATERIAL_RATIO
        problems.append(
            f"高消耗低效素材：「{_short(poor['name'])}」消耗 {_money(poor.get('spend'))}"
            f"（占素材消耗 {share:.0f}%），ROI 仅 {roi_text}，拉低整体"
            f"（依据：消耗 {_money(poor.get('spend'))} > ¥{POOR_MATERIAL_SPEND:,.0f}"
            f" 且 ROI {roi_text} < 账户实际 ROI {_ratio(metrics.roi)} × 0.8 = {cutoff:.2f}；"
            "官方补充：素材是否低质要看**持续多天低跑量**，不能用单场 ROI 判定）"
        )

    # 5) 直播间承接：在线/转化率与自身基线对比（见 baselines 部分）

    if not problems:
        if roi_ok:
            problems.append(
                f"未发现明显异常：ROI {metrics.roi:.2f} 达标，消耗节奏稳定"
            )
        else:
            problems.append("未发现新的异常信号，继续观察")
    return problems


def build_adjustments(
    event: MonitorEvent,
    history: list[dict],
    roi_target: float | None,
    split: dict | None = None,
) -> list[str]:
    """给出落到「具体对象 + 具体动作 + 验证窗口」的执行方案（都需你确认）。"""
    metrics = event.metrics
    threshold = roi_target  # 可能为 None：目标没读到就不拿它做判断
    ratio = spend_split_ratio(split)
    plans: list[str] = []

    if event.source == "cdp-error" or event.freshness != "fresh":
        return ["先恢复直播大屏数据读取，拿到数据再判断，本轮不做任何调整。"]

    poor, best = _pick_materials(split, threshold, account_roi=metrics.roi)
    roi = metrics.roi

    # 1) 素材处置（最具体，先落这里）
    if poor is not None:
        roi_text = f"{float(poor['roi']):.2f}" if poor.get("roi") is not None else "无"
        target_text = (
            f"，把预算挪给「{_short(best[0]['name'])}」（ROI {float(best[0]['roi']):.2f}）"
            if best and best[0].get("roi") is not None
            else ""
        )
        base_roi = metrics.roi if metrics.roi is not None else threshold
        cutoff = (base_roi or 0.0) * POOR_MATERIAL_RATIO
        plans.append(
            f"素材：「{_short(poor['name'])}」消耗 {_money(poor.get('spend'))}、"
            f"ROI {roi_text} 低于账户实际 ROI {_ratio(metrics.roi)} × 0.8 = {cutoff:.2f}"
            "。⚠️ 按官方口径：**投放中不要直接删除/暂停高跑量素材**"
            "（官方《净成交出价-素材评估思路》：素材之间相互配合，"
            "有的承担跑量责任、有的承担转化责任，贸然删高跑量素材会让系统探索范围变小、"
            "跑量规模下滑，整体 GMV 和 ROI 反而变差）。"
            "正确做法：① 先判断它是不是「持续多天低跑量」——单场 ROI 低不等于该清；"
            "② 想刺激它起量，用追投**下调 ROI 目标**加速激活，而不是删"
        )

    # 2) 追投占比
    if ratio is not None and ratio > 50:
        plans.append(
            f"追投：当前追投/调控占 {ratio:.1f}%。把追投整体下调 20%～30%，"
            "腾出的量给基础计划；10 分钟后看基础消耗是否回升（目标：基础占比 > 40%）"
        )

    # 3) ROI
    if roi is not None and threshold is None:
        plans.append(
            f"ROI：当前整体 {roi:.2f}，但没读到该计划的 ROI 目标，本轮无法判断是否达标。"
            "先去计划里确认目标，再决定收缩还是放量"
        )
    elif roi is not None and roi < threshold:
        plans.append(
            f"ROI：先按上面两步收缩，10～20 分钟观察 ROI 能否回到 {threshold:.2f}。"
            "注意官方口径：控成本追投的 ROI 达成和累计消耗直接相关，"
            "**累计消耗未达到 10 个转化成本时，ROI 没达标属正常探索期**，别急着判定失败"
        )

    # 4) 消耗异常
    if event.spend_delta is not None and abs(event.spend_delta) < 1:
        plans.append(
            "消耗：先确认预算没撞线、计划还在投放；确认没问题后，"
            "一边观察其他有潜力但没放量的素材，一边新建 1 条追投计划测试"
        )
    elif (
        event.spend_delta is not None
        and metrics.spend > 0
        and event.spend_delta > max(300.0, metrics.spend * 0.05)
    ):
        plans.append(
            f"流速：{window_text if (window_text := (f"近 {event.minutes_since_previous:.0f} 分钟" if event.minutes_since_previous else "本周期")) else "本周期"}"
            f"消耗加快（+{_money(event.spend_delta)}）。先找跑量的那条计划，"
            "降预算控流速，10 分钟看 ROI 是否止跌"
        )

    # 5) 承接
    if metrics.online_viewers <= 5:
        plans.append(
            f"承接：在线仅 {metrics.online_viewers} 人。先别加量，检查直播画面和话术节奏；"
            "承接稳住再加预算"
        )

    if roi is not None and threshold is not None and roi >= threshold:
        plans = [
            f"ROI 达标（{roi:.2f} ≥ {threshold:.2f}）：保持现状继续给量，"
            "记录本小时有效计划和素材，不要动"
        ] + plans

    if not plans:
        plans.append("维持现状，下一个 5 分钟窗口再判断")
    plans.append(
        "素材探索期（官方口径）：新素材上传后系统会自动探索，**探索期约 3 日**；"
        "3 日内跑不动属正常，不要急着判失败或删除"
    )
    plans.append(
        "合规提醒（官方《全域投放-推直播间产品手册》）："
        "① 调整目标 ROI 间隔 ≥1 小时、单次幅度不超过 ±10%，否则不享受成本保障；"
        "② **不要用「卡预算 / 频繁起停」来代替一键控量**，会导致反复冷启影响效果；"
        "③ **避免小额预算多次小幅频繁上调**，会影响跑量和效果；"
        "④ 素材循序渐进优化，**不要骤然大量删除**（会让投放场景剧烈变化、可能掉量、ROI 骤跌）；"
        "⑤ 新素材投后**不要短期探索就立即删除**（既付出探索成本又拿不到正向收益）；"
        "⑥ 不要频繁调控，前期数据积累阶段效果不稳定属正常，保持耐心"
    )
    plans.append("以上动作都需要你确认后才会执行，系统当前保持只读。")
    return plans


ACTION_LABELS = {
    "pause_plan": "暂停计划",
    "enable_plan": "启用计划",
    "update_plan_budget": "修改预算",
    "update_plan_bid": "修改出价",
    "create_plan": "新建计划",
    "copy_plan": "复制计划",
    "delete_plan": "删除计划",
    "edit_plan": "编辑计划",
    "update_targeting": "修改定向",
    "update_schedule": "修改投放时段",
    "bind_existing_material": "绑定素材",
    "unbind_existing_material": "解绑素材",
}


def action_label(op: dict) -> str:
    name = str(op.get("action_name") or "")
    return ACTION_LABELS.get(name, name or "操作")


def action_intent(op: dict) -> str:
    """判断这次操作是收缩、放量还是普通调整。"""
    name = str(op.get("action_name") or "")
    if name in ("pause_plan", "delete_plan"):
        return "收缩"
    if name in ("enable_plan", "create_plan", "copy_plan"):
        return "放量"
    summary = str(op.get("summary") or "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*→\s*([0-9]+(?:\.[0-9]+)?)", summary)
    if match:
        before, after = float(match.group(1)), float(match.group(2))
        if after < before:
            return "收缩"
        if after > before:
            return "放量"
    return "调整"


def _op_time(op: dict) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(op.get("created_at") or ""))
    except Exception:  # noqa: BLE001
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def platform_op_at(op: dict) -> datetime | None:
    """千川日志里的时间字符串（北京时间，无时区信息）。"""
    try:
        value = datetime.fromisoformat(str(op.get("time") or ""))
    except Exception:  # noqa: BLE001
        return None
    return value.replace(tzinfo=BEIJING)


def summarize_platform_ops(ops: list[dict]) -> str:
    """把一批平台操作归类成一句话，用于复盘。"""
    buckets: dict[str, int] = {}
    details: list[str] = []
    for op in ops:
        text = "；".join(op.get("details") or [])
        if "已暂停" in text:
            buckets["暂停调控"] = buckets.get("暂停调控", 0) + 1
        elif op.get("type") == "新建" and "素材追投" in text:
            buckets["新建素材追投"] = buckets.get("新建素材追投", 0) + 1
        match = re.search(r"调控预算：([0-9.]+)元(?:\s*->\s*([0-9.]+)元)?", text)
        if match:
            if match.group(2):
                details.append(f"调控预算 {match.group(1)}→{match.group(2)} 元")
            else:
                details.append(f"调控预算 {match.group(1)} 元")
        roi_match = re.search(r"综合营销ROI目标：([0-9.]+)\s*->\s*([0-9.]+)", text)
        if roi_match:
            details.append(f"ROI目标 {roi_match.group(1)}→{roi_match.group(2)}")
    parts = [f"{name} {count} 条" for name, count in buckets.items()]
    if details:
        parts.append("；".join(details[:3]))
    return "、".join(parts) if parts else "操作明细见上"


def _fmt_money(value: str) -> str:
    try:
        return f"¥{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def describe_platform_op(op: dict) -> dict | None:
    """把一个千川平台操作翻译成「运营在做什么 + 为什么 + 要验证什么」。"""
    text = "；".join(op.get("details") or [])
    stamp = str(op.get("time") or "")[11:16]
    op_type = str(op.get("type") or "")

    budget = re.search(r"调控预算：([0-9.]+)元(?:\s*->\s*([0-9.]+)元)?", text)
    roi_goal = re.search(r"综合营销ROI目标：([0-9.]+)\s*->\s*([0-9.]+)", text)
    roi_goal_new = re.search(r"综合营销ROI目标：([0-9.]+)", text)

    if "已暂停" in text and "调控" in text:
        return {
            "kind": "暂停调控",
            "action": f"{stamp}　暂停调控",
            "why": "止损动作：这条追投大概率 ROI 不达标或消耗跑太快，先掐掉它把成本控住",
            "watch": "暂停后 10～20 分钟，整体 ROI 是否回升、基础计划消耗能不能接上",
        }
    if op_type == "新建" and "素材追投" in text:
        budget_text = _fmt_money(budget.group(1)) if budget else "未标注"
        hot = "优质" in text or "爆款" in text
        return {
            "kind": "新建追投",
            "action": f"{stamp}　新建素材追投（预算 {budget_text}）",
            "why": (
                "放量/测试动作：用新素材找增量"
                + ("，任务名标了『优质/爆款』，是从已有高潜素材里挑的" if hot else "")
            ),
            "watch": "这条新追投能否跑出消耗且 ROI 达到目标；跑不动就要换素材",
        }
    if budget and budget.group(2) and "调控预算" in text:
        old, new = float(budget.group(1)), float(budget.group(2))
        if new > old:
            return {
                "kind": "加预算",
                "action": f"{stamp}　调控预算 {_fmt_money(budget.group(1))} → {_fmt_money(budget.group(2))}",
                "why": "加量动作：这条追投表现达标，运营在给好素材更多预算",
                "watch": "加预算后 ROI 能否维持；掉太多说明直播间承接不住",
            }
        return {
            "kind": "减预算",
            "action": f"{stamp}　调控预算 {_fmt_money(budget.group(1))} → {_fmt_money(budget.group(2))}",
            "why": "收缩动作：这条追投不达预期，先减量观察，避免继续吃预算",
            "watch": "减量后整体 ROI 是否回升、消耗是否还在可控范围",
        }
    if roi_goal:
        old, new = float(roi_goal.group(1)), float(roi_goal.group(2))
        if new < old:
            return {
                "kind": "放宽ROI目标",
                "action": f"{stamp}　综合营销ROI目标 {old:.2f} → {new:.2f}",
                "why": "换量动作：当前出价拿不到量，运营宁可降一点 ROI 要求，也要把消耗跑起来",
                "watch": "消耗是否起来、成交能不能同比例跟上；整体 ROI 水位会不会被拉低",
            }
        return {
            "kind": "收紧ROI目标",
            "action": f"{stamp}　综合营销ROI目标 {old:.2f} → {new:.2f}",
            "why": "提质动作：主动提高 ROI 要求，压掉低效流量",
            "watch": "目标提高后消耗会不会掉太快，量价能不能平衡",
        }
    if roi_goal_new:
        return {
            "kind": "设置ROI目标",
            "action": f"{stamp}　综合营销ROI目标 {roi_goal_new.group(1)}",
            "why": "设定目标：给这条追投定一个 ROI 门槛",
            "watch": "这条追投能否达到该目标，达不到要考虑换素材",
        }
    return None


def analyze_platform_operations(
    ops: list[dict],
    metrics,
    roi_target: float | None,
    split: dict | None,
) -> list[str]:
    """从运营视角分析平台上这些操作：为什么做、在什么背景下做、要验证什么。"""
    described = []
    seen_keys = set()
    for op in ops:
        item = describe_platform_op(op)
        if not item:
            continue
        # 同一批日志里常有多条同类型操作，别把同一句话重复贴三遍
        key = (item.get("kind"), str(item.get("action") or "")[6:])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        described.append(item)
    if not described:
        return []

    threshold = roi_target  # 可能为 None：不要编目标
    ratio = spend_split_ratio(split)
    context_bits: list[str] = []
    if metrics.roi is not None:
        if threshold is not None:
            context_bits.append(f"整体 ROI {metrics.roi:.2f}（目标 {threshold:.2f}）")
        else:
            context_bits.append(f"整体 ROI {metrics.roi:.2f}（目标未读到）")
    if ratio is not None:
        context_bits.append(f"追投占比 {ratio:.1f}%")
    context = "、".join(context_bits)

    lines: list[str] = []
    for item in described[:5]:
        line = f"- {item['action']}：**{item['why']}**"
        if context:
            line += f"（当时账户背景：{context}）"
        line += f"；要验证：{item['watch']}"
        lines.append(line)

    kinds = [item["kind"] for item in described]
    if any(k in ("暂停调控", "减预算", "收紧ROI目标") for k in kinds) and any(
        k in ("新建追投", "加预算") for k in kinds
    ):
        main = "一边收缩低效追投、一边补新素材测试，主线是「控成本 + 找增量」"
    elif any(k in ("暂停调控", "减预算") for k in kinds):
        main = "以收缩为主，主线是「先把成本控住，再看基础计划能不能接量」"
    elif any(k in ("新建追投", "加预算") for k in kinds):
        main = "以放量为主，主线是「给达标素材更多量，把消耗打上去」"
    elif any(k in ("放宽ROI目标",) for k in kinds):
        main = "在放宽目标换量，主线是「量优先，但要盯住 ROI 水位」"
    else:
        main = "以参数微调为主"
    lines.append(f"- 整体运营思路：{main}。")
    return lines


def roi_trend_analysis(
    previous_roi: float | None,
    current_roi: float | None,
    ops: list[dict],
) -> str | None:
    """ROI 明显变化时给出归因，尤其是上涨时要说明可能原因。"""
    if previous_roi is None or current_roi is None:
        return None
    before = float(previous_roi)
    delta = float(current_roi) - before
    if abs(delta) < 0.02:
        return None
    if delta < 0:
        base = f"ROI 下滑：{before:.2f} → {float(current_roi):.2f}（{delta:+.2f}）"
    else:
        base = f"ROI 回升：{before:.2f} → {float(current_roi):.2f}（{delta:+.2f}）"

    causes: list[str] = []
    for op in ops:
        text = "；".join(op.get("details") or [])
        if "已暂停" in text:
            causes.append("暂停了调控中的追投")
        money = re.search(r"([0-9.]+)元\s*->\s*([0-9.]+)元", text)
        if money and "调控预算" in text:
            if float(money.group(2)) < float(money.group(1)):
                causes.append("下调了追投预算")
            else:
                causes.append("上调了追投预算")
        roi_match = re.search(r"综合营销ROI目标：([0-9.]+)\s*->\s*([0-9.]+)", text)
        if roi_match:
            if float(roi_match.group(2)) < float(roi_match.group(1)):
                causes.append("下调了 ROI 目标")
            else:
                causes.append("上调了 ROI 目标")

    unique = list(dict.fromkeys(causes))[:4]
    if unique:
        return (
            base
            + f"。近 5 分钟操作（{'、'.join(unique)}）是主要可能原因，继续观察能否稳住。"
        )
    if delta > 0:
        return base + "。近 5 分钟没有操作，属于自然回升（素材/人群/直播间承接变好），先保持不动观察。"
    return base + "。近 5 分钟没有操作，需要排查素材衰退或直播间接不住量。"


def analyze_operation(op: dict, history: list[dict], metrics) -> str:
    """记录之后还要分析：拿操作前的最后一次盯盘数据和当前数据做对比。"""
    op_at = _op_time(op)
    baseline = None
    for entry in history:
        try:
            entry_at = datetime.fromisoformat(str(entry.get("created_at") or ""))
        except Exception:  # noqa: BLE001
            continue
        if entry_at.tzinfo is None:
            entry_at = entry_at.replace(tzinfo=UTC)
        if op_at is not None and entry_at > op_at:
            break
        baseline = entry

    intent = action_intent(op)
    now_roi = metrics.roi
    before_roi = (baseline or {}).get("roi")
    if before_roi is None or now_roi is None:
        return f"动作类型：{intent}。刚执行完，效果还没反映到数据上，下个周期再判断。"

    before_roi = float(before_roi)
    delta = now_roi - before_roi
    if delta > 0.02:
        trend = "回升"
    elif delta < -0.02:
        trend = "继续下滑"
    else:
        trend = "基本持平"

    if intent == "收缩":
        verdict = (
            "收缩有效，ROI 止跌回升，保持观察"
            if delta > 0.02
            else "收缩后仍未止跌，考虑继续降量或换素材"
            if delta < -0.02
            else "收缩后 ROI 稳住，继续观察基础消耗能否起来"
        )
    elif intent == "放量":
        verdict = (
            "放量后 ROI 下滑，建议收回部分量"
            if delta < -0.02
            else "放量暂未伤害 ROI，可以继续给量"
        )
    else:
        verdict = (
            "调整后 ROI 回升，继续观察"
            if delta > 0.02
            else "调整后 ROI 继续下滑，需要再处理"
            if delta < -0.02
            else "调整后 ROI 平稳，继续观察"
        )

    return (
        f"动作类型：{intent}。执行前 ROI {before_roi:.2f} → 现在 {now_roi:.2f}"
        f"（{trend}），{verdict}。"
    )


def build_watch_report(
    event: MonitorEvent,
    history: list[dict],
    roi_target: float | None,
    operations: list[dict],
    plan=None,
    split: dict | None = None,
    platform_ops: list[dict] | None = None,
    baselines: dict | None = None,
    plan_splits: list[dict] | None = None,
    stagnant: bool = False,
    stagnant_note: str = "",
    resume_note: str = "",
    audit_notes: list[str] | None = None,
    threshold_lines: dict | None = None,
) -> dict:
    now = datetime.now(UTC)
    metrics = event.metrics
    previous = history[-1] if history else None
    problems = detect_problems(event, history, roi_target, split)
    adjustments = build_adjustments(event, history, roi_target, split)
    trend = roi_trend_analysis(
        (previous or {}).get("roi") if previous else None,
        metrics.roi,
        platform_ops or [],
    )
    if trend:
        problems.append(trend)
    skipped_baselines: list[str] = []
    if baselines:
        baseline_issues, skipped_baselines = baseline_problems(
            metrics, baselines, len(history)
        )
        problems = problems + baseline_issues
    # 注意：投放管理页的「基础 vs 整体」是【当日累计】口径，和直播大屏的
    # 【当前场次】口径不同，直接放进同一张报表会自相矛盾。这里不再渲染它，
    # 场次口径的基础/追投拆分统一由「投放结构拆分」区块输出（见下方）。
    split_section = ""

    def roi_cell() -> str:
        text = _ratio(metrics.roi)
        if previous and previous.get("roi") is not None and metrics.roi is not None:
            delta = metrics.roi - float(previous["roi"])
            if abs(delta) >= 0.005:
                text += f"（{delta:+.2f}）"
        return text

    def spend_cell() -> str:
        text = _money(metrics.spend)
        if event.spend_delta:
            text += f"（{_delta(event.spend_delta)}）"
        return text

    plan_id = getattr(plan, "id", None)
    room_name = getattr(event.metrics, "room_name", None) or getattr(plan, "account_name", None)
    header_bits = []
    if room_name:
        header_bits.append(str(room_name))
    if roi_target is not None:
        header_bits.append(f"目标 ROI {_ratio(roi_target)}")
    started = getattr(event, "live_started_at", None)
    if started is not None:
        try:
            header_bits.append(
                "场次 " + started.astimezone(BEIJING).strftime("%m-%d %H:%M 开播")
            )
        except Exception:  # noqa: BLE001
            pass
    status_text = "直播中" if event.plan_status != "ended" else "⚠️ 已结束（读到的是收场快照）"
    header_bits.append(f"状态 {status_text}")
    header_bits.append(f"数据源 {event.source}")
    if event.freshness != "fresh":
        header_bits.append(f"新鲜度 {event.freshness}")

    lines: list[str] = []
    lines.append(
        f"## 直播盯盘报表 · {now.astimezone(BEIJING).strftime('%m-%d %H:%M')}"
    )
    lines.append("")
    lines.append("> " + "　|　".join(header_bits))
    lines.append("")
    if resume_note:
        lines.append(f"> ⏱️ **已恢复盯盘**：{resume_note}")
        lines.append("")
    lines.append("### 实时数据")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | ---: |")
    lines.append(f"| 综合营销 ROI | {roi_cell()} |")
    lines.append(f"| 综合成本 | {spend_cell()} |")
    lines.append(f"| 净成交金额 | {_money(metrics.gmv)} |")
    lines.append(f"| GPM | {_money(metrics.gpm)} |")
    lines.append(f"| 实时在线人数 | {metrics.online_viewers} |")
    lines.append(f"| 成交订单数 | {metrics.orders} |")
    lines.append("")
    if split_section:
        lines.append(split_section)
        lines.append("")
    lines.append("### 投放结构拆分（基础投放 / 追投调控 / 整体）")
    lines.append("")
    split_detail = (split or {}).get("split") or {}
    if split_detail and not split_detail.get("split_error"):
        window = split_detail.get("split_window") or {}
        lines.append("| 指标 | 基础投放 | 追投调控 | 整体 |")
        lines.append("| --- | ---: | ---: | ---: |")
        lines.append(
            f"| 消耗(元) | {_money(split_detail.get('basic_spend'))} "
            f"| {_money(split_detail.get('assist_spend'))} "
            f"| {_money(split_detail.get('total_spend'))} |"
        )
        lines.append(
            f"| 支付ROI | {_ratio(split_detail.get('basic_roi'))} "
            f"| {_ratio(split_detail.get('assist_roi'))} "
            f"| {_ratio(split_detail.get('total_roi'))} |"
        )
        lines.append(
            f"| 净成交金额(元) | {_money(split_detail.get('basic_gmv'))} "
            f"| {_money(split_detail.get('assist_gmv'))} "
            f"| {_money(split_detail.get('total_gmv'))} |"
        )
        lines.append(
            f"| 净成交订单数 | {_fmt_int(split_detail.get('basic_orders'))} "
            f"| {_fmt_int(split_detail.get('assist_orders'))} "
            f"| {_fmt_int(split_detail.get('total_orders'))} |"
        )
        lines.append(
            "| GPM(元) | 不可拆分 | 不可拆分 "
            f"| {_money(metrics.gpm)} |"
        )
        lines.append("")
        ratio = spend_split_ratio(split)
        if ratio is not None:
            lines.append(
                f"- 追投调控（素材追投）占总消耗 **{ratio:.1f}%**"
                "（官方建议控成本追投占账户总消耗约 25%）"
            )
        other = split_detail.get("other_spend")
        if other is not None and abs(float(other)) >= 1:
            lines.append(
                f"- 其它调控（一键调速 / 搜索抢首屏等）消耗 {_money(float(other))}，"
                "不计入「基础投放」和「追投调控」两列"
            )
        if window.get("start"):
            lines.append(
                f"- 拆分口径：{window.get('start')} → {window.get('end')}"
                "（与直播大屏同一个场次时间窗）"
            )
        lines.append(
            "- 数据来源：千川「素材数据」接口（**素材口径**）。"
            "它只统计素材维度的消耗，和大屏的「综合成本」不是同一个口径，"
            "**同一张表内只做纵向对比（基础 vs 追投 vs 整体），不要拿它和大屏数字相减**；"
            "下面的「追投占比」指的是占素材口径消耗，不等于占账户总消耗"
        )
        # 把两套口径的实际差额算出来，别让用户自己猜
        board_spend = getattr(metrics, "spend", None)
        mat_spend = split_detail.get("total_spend")
        if board_spend and mat_spend and float(board_spend) > 0:
            coverage = float(mat_spend) / float(board_spend) * 100
            gap_note = (
                f"- ⚠️ 口径差额（本次实测）：素材口径 {_money(float(mat_spend))} "
                f"vs 大屏综合成本 {_money(float(board_spend))}，"
                f"素材口径只覆盖了大屏的 **{coverage:.0f}%**"
            )
            if coverage < 95:
                gap_note += (
                    "（大屏还包含素材维度之外的消耗，两者不能互相校验；"
                    "看占比时记住分母是素材口径）"
                )
            lines.append(gap_note)
        lines.append(
            "- **GPM 为什么不能拆**：GPM = 净成交金额 ÷ 直播间观看次数 × 1000，"
            "千川只对「消耗 / 成交金额 / ROI / 订单数」提供基础与追投拆分，"
            "观看次数没有基础 / 追投口径，所以 GPM 只能给整体值（硬拆会算错，宁可不拆）"
        )
    elif split:
        basic = float(split.get("basic_spend") or 0)
        assist = float(split.get("assist_spend") or 0)
        ratio = spend_split_ratio(split)
        lines.append("| 项目 | 金额 |")
        lines.append("| --- | ---: |")
        lines.append(f"| 基础计划消耗 | {_money(basic)} |")
        lines.append(f"| 追投/调控消耗 | {_money(assist)} |")
        if ratio is not None:
            lines.append(f"| 追投占比 | {ratio:.1f}% |")
        lines.append("")
        lines.append(
            "- ⚠️ 本轮只读到消耗拆分，ROI / 成交 / 订单的拆分指标不完整，"
            "不做拆分结论（避免口径错配）"
        )
    else:
        lines.append("- 暂未读取到投放结构拆分（基础 / 追投调控）")
    lines.append("")
    passed, verify_issues = verify_data(metrics, split, plan_splits)
    if stagnant:
        passed = False
        verify_issues = verify_issues + [
            f"数据停滞：{stagnant_note or '消耗连续多个周期没有变化'}"
            "（场次可能已结束，或大屏没刷新——这种情况下出的分析没有意义）"
        ]
    if not passed:
        # 数据没过校验：只报数据，不出分析
        lines.append("### 数据校验（未通过）")
        lines.append("")
        for item in verify_issues:
            lines.append(f"- ❌ {item}")
        lines.append("")
        lines.append("> **数据未通过校验，本轮不出问题判断和调整方案。**"
                     "请先核对数据来源，确认无误后再看分析。")
        lines.append("")
        lines.append("### 原始读数（供你核对）")
        lines.append("")
        lines.append(f"- 消耗 {_money(metrics.spend)} / 成交 {_money(metrics.gmv)} / "
                     f"订单 {metrics.orders} / ROI {_ratio(metrics.roi)}")
        lines.append(f"- 曝光 {metrics.exposure_count or 0:,} / 观看次数 {metrics.view_count or 0:,} / "
                     f"商品点击 {metrics.product_clicks or 0:,}")
        lines.append(f"- GPM {_money(metrics.gpm)} / 在线 {metrics.online_viewers}")
        lines.append("")
        lines[0] = lines[0].replace("## 直播盯盘报表", "## ⚠️ 直播盯盘报表（数据未通过校验）")
        return {
            "id": str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "captured_at": event.captured_at.isoformat(),
        "live_started_at": (
            getattr(event, "live_started_at", None).isoformat()
            if getattr(event, "live_started_at", None)
            else None
        ),
        "live_room_id": getattr(event.metrics, "live_room_id", None),
            "level": event.level,
            "source": event.source,
            "roi": metrics.roi,
            "spend": metrics.spend,
            "gmv": metrics.gmv,
            "gpm": metrics.gpm,
            "online_viewers": metrics.online_viewers,
            "orders": metrics.orders,
            "spend_delta": event.spend_delta,
            "cpm": _cpm(metrics),
            "exposure_view_rate": getattr(metrics, "exposure_view_rate", None),
            "view_conversion_rate": getattr(metrics, "view_conversion_rate", None),
            "views": metrics.views,
            "roi_target": roi_target,
            "plan_id": plan_id,
            "room_name": str(room_name) if room_name else None,
            "spend_split": split,
            "problems": [],
            "adjustments": [],
            "operations": operations,
            "report_markdown": "\n".join(lines),
            "note": getattr(event, "reason", ""),
            "self_check": verify_issues,
            "verify_passed": False,
        }

    lines.append("### 诊断结论（逐层归因 + 交叉验证）")
    lines.append("")
    diag = diagnose(
        metrics,
        roi_target,
        baselines=baselines,
        spend_split=split,
        plan_splits=plan_splits,
        room_name=str(room_name) if room_name else None,
        spend_delta=event.spend_delta,
        lines=threshold_lines,
    )
    if diag:
        for d in diag:
            lines.append(d.render())
            lines.append("")
    else:
        lines.append("- 本场各项指标正常，未发现需要处理的问题")
        lines.append("")

    lines.append("### 其他信号")
    lines.append("")
    for item in problems:
        if "：" in item:
            label, detail = item.split("：", 1)
            lines.append(f"- **{label}** — {detail}")
        elif "低于目标" in item:
            lines.append("- **ROI 未达标** — " + item.removeprefix("ROI "))
        else:
            lines.append(f"- {item}")
    lines.append("")
    lines.append("### 调整方案（需你确认）")
    lines.append("")
    for index, item in enumerate(adjustments, 1):
        lines.append(f"{index}. {item}")
    lines.append("")
    lines.append("### 操作日志")
    lines.append("")

    def op_line(op: dict) -> str:
        created = op.get("created_at") or ""
        try:
            created = (
                datetime.fromisoformat(created).astimezone(BEIJING).strftime("%m-%d %H:%M")
            )
        except Exception:  # noqa: BLE001
            pass
        summary = op.get("summary") or ""
        suffix = f"　{summary}" if summary else ""
        status_text = {"succeeded": "执行成功", "failed": "执行失败"}.get(
            str(op.get("status")), str(op.get("status"))
        )
        return f"{created}　{action_label(op)}　{status_text}{suffix}"

    window_start = now - timedelta(minutes=5)
    fresh_ops: list[dict] = []
    for op in operations:
        try:
            created = datetime.fromisoformat(str(op.get("created_at") or ""))
        except Exception:  # noqa: BLE001
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created >= window_start:
            fresh_ops.append(op)

    # 平台日志（千川「详情 → 日志」，包含人工/其他工具的操作）
    def platform_line(op: dict) -> str:
        raw = str(op.get("time") or "")
        # 带日期：只显示 23:45:14 会被当成今天的操作（10-09 23:45 看着就像今天 23:45）
        stamp = raw[5:16] if len(raw) >= 16 else raw
        detail = "；".join((op.get("details") or [])[:4]) or str(op.get("summary") or "")
        return f"{stamp}　{op.get('type')}　{detail}"

    today_text = now.astimezone(BEIJING).strftime("%Y-%m-%d")

    def is_today(op: dict) -> bool:
        return str(op.get("time") or "").startswith(today_text)

    logs = platform_ops or []
    fresh_platform = []
    for op in logs:
        op_at = platform_op_at(op)
        if op_at is not None and op_at >= now.astimezone(BEIJING) - timedelta(minutes=5):
            fresh_platform.append(op)

    if logs:
        lines.append("**平台操作（千川日志）**")
        if fresh_platform:
            lines.append(f"- 近 5 分钟有 {len(fresh_platform)} 条：")
            for op in fresh_platform[:8]:
                lines.append(f"- {platform_line(op)}")
            analyzed_ops = fresh_platform
        else:
            lines.append("- 近 5 分钟无操作变化")
            latest = logs[0]
            if is_today(latest):
                lines.append(f"- 最近一次操作（今天）：{platform_line(latest)}")
            else:
                lines.append(
                    f"- 今天没有操作记录；**最近一次操作是 {platform_line(latest)}**"
                    "（不是今天的）"
                )
            analyzed_ops = logs[:3]
        lines.append("")
        analysis = analyze_platform_operations(analyzed_ops, metrics, roi_target, split)
        lines.append("**操作分析（运营视角）**")
        if analysis:
            lines.extend(analysis)
        else:
            # 别只留一个空标题：说清为什么没分析，并给出人工要看的点
            kinds = "、".join(
                sorted({str(op.get("type") or "未知类型") for op in analyzed_ops})
            )
            lines.append(
                f"- 这些操作（{kinds}）暂不在自动分析的覆盖范围内，"
                "请人工确认：改的是什么对象、改前改后、以及接下来 10～20 分钟"
                "整体 ROI / 消耗有没有跟着变化"
            )
        lines.append("")

    if fresh_ops:
        lines.append("**系统执行记录**")
        lines.append(f"- 近 5 分钟有 {len(fresh_ops)} 条操作变化：")
        for op in fresh_ops:
            lines.append(f"- {op_line(op)}")
            lines.append(f"- 分析：{analyze_operation(op, history, metrics)}")
    elif operations:
        lines.append("**系统执行记录**")
        lines.append(f"- 最近一次操作：{op_line(operations[0])}")
        lines.append(f"- 分析：{analyze_operation(operations[0], history, metrics)}")
    elif not logs:
        lines.append("- 千川日志与本系统均暂无操作记录")
    lines.append("")

    # 输出前自检
    issues = self_check(metrics, problems, split)
    note_list = list(audit_notes or [])
    if skipped_baselines:
        # 样本不足时以前是静默跳过的，用户分不清"没问题"和"没基准可比"
        note_list.append(
            "样本不足（本账户历史 < 5 次采样）："
            + "、".join(skipped_baselines)
            + " —— **本轮不做绝对水位判断**，只看相对变化和官方硬约束；"
            "等历史样本够了会自动改用「本账户自身分位数」"
        )
    lines.append(render_self_check(issues, note_list))
    if issues and lines and lines[0].startswith("## 直播盯盘报表"):
        lines[0] = lines[0].replace("## 直播盯盘报表", "## ⚠️ 直播盯盘报表（自检未通过）")

    return {
        "id": str(uuid.uuid4()),
        "created_at": now.isoformat(),
        "captured_at": event.captured_at.isoformat(),
        "level": event.level,
        "source": event.source,
        "roi": metrics.roi,
        "spend": metrics.spend,
        "gmv": metrics.gmv,
        "gpm": metrics.gpm,
        "online_viewers": metrics.online_viewers,
        "orders": metrics.orders,
        "spend_delta": event.spend_delta,
        "cpm": _cpm(metrics),
        "exposure_view_rate": getattr(metrics, "exposure_view_rate", None),
        "view_conversion_rate": getattr(metrics, "view_conversion_rate", None),
        "views": metrics.views,
        "roi_target": roi_target,
        "plan_id": plan_id,
        "room_name": str(room_name) if room_name else None,
        "spend_split": split,
        "problems": problems,
        "adjustments": adjustments,
        # 注意区分两个"操作"：
        #   operations          = 工具自己执行的操作（只读模式恒为空）
        #   platform_operations = 千川平台日志里「你手动做的操作」（结构化保存）
        # 学习/回看要的是后者 —— 之前只把它写进 markdown 文本，没法统计。
        "operations": operations,
        "platform_operations": list(platform_ops or []),
        "report_markdown": "\n".join(lines),
        "live_started_at": (
            getattr(event, "live_started_at", None).isoformat()
            if getattr(event, "live_started_at", None)
            else None
        ),
        "live_room_id": getattr(event.metrics, "live_room_id", None),
        "session_status": event.plan_status,
        "note": getattr(event, "reason", ""),
        "self_check": issues,
        "verify_passed": True,
    }


class LiveWatchService:
    """打开直播盯盘后每 interval 秒出一份盯盘报表。"""

    def __init__(
        self,
        monitor_service,
        hub,
        store: LiveWatchLogStore | None = None,
        interval_seconds: int = 300,
        plan_provider=None,
        plan_refresher=None,
        spend_split_provider=None,
        platform_log_provider=None,
        plan_split_provider=None,
        snapshot_refresher=None,
        session_state_provider=None,
        profile_provider=None,
        session_end_handler=None,
        alert_notifier=None,
        cdp_reconnector=None,
        tick_timeout_seconds: float = 90.0,
        alert_repeat_seconds: float = 6 * 3600,
        state_path: Path = LIVE_WATCH_STATE_PATH,
    ) -> None:
        self.state_path = state_path
        self.monitor_service = monitor_service
        self.hub = hub
        # 默认用 SQLite：JSON 版每 5 分钟要全量重写 5MB，越跑越慢
        self.store = store or SqliteWatchLogStore()
        self.interval_seconds = interval_seconds
        self.plan_provider = plan_provider
        self.plan_refresher = plan_refresher
        self.spend_split_provider = spend_split_provider
        self.platform_log_provider = platform_log_provider
        self.plan_split_provider = plan_split_provider
        # 自检用：怀疑读数没刷新时，真的去把大屏刷新一遍再读一次
        self.snapshot_refresher = snapshot_refresher
        # 自检用：大屏头部经常不渲染，读不到「已结束」。这个回调去投放管理页
        # 确认「当前到底有没有在播的场次」，避免把已结束的收场快照当直播中。
        self.session_state_provider = session_state_provider
        # 你在「决策」窗口设的阈值存在投放策略里，这里取它
        self.profile_provider = profile_provider
        # 本场结束后：出复盘 → 停盯盘（下一场要手动开）
        self.session_end_handler = session_end_handler
        self.tick_timeout_seconds = tick_timeout_seconds
        self._ended_handled_for: str | None = None
        self._pending_stop_reason: str | None = None
        # 异常告警（读不到数据 / 数据停滞）。同类问题只报一次，恢复了才会再报。
        self.alert_notifier = alert_notifier
        self._alerted_for: str | None = None
        # 同类问题不刷屏，但也不能只报一次就永远安静——故障持续时每 N 小时提醒一次
        self.alert_repeat_seconds = alert_repeat_seconds
        self._alerted_at = None
        # CDP 断了自动重连：连续失败到阈值后，尝试自己把调试浏览器拉起来。
        # （用户反馈过：关电脑 / 浏览器被关之后，工具不会自己恢复读数据。）
        self.cdp_reconnector = cdp_reconnector
        self.reconnect_after_failures = 3
        self.reconnect_cooldown_seconds = 600.0
        self._last_reconnect_at: datetime | None = None
        self._task: asyncio.Task | None = None
        self._last_run: datetime | None = None
        self._tick_count = 0
        self._last_live_started: datetime | None = None
        self._recent_spends: list[float] = []
        self._stagnant_ticks = 0
        # 最后一次看到"消耗增长"的时间 —— 用来兜底判断本场是否已结束
        self._last_spend_value = 0.0
        self._last_spend_growth_at: datetime | None = None
        # --- 断线恢复相关 ---------------------------------------------------
        # desired_running：用户「想不想让它跑」。只有用户点「停止盯盘」才会变 False；
        # 关窗口 / 关机 / 后端重启都不算停止，恢复后要接着跑。
        persisted = self._read_state()
        self.desired_running: bool = bool(
            persisted.get("desired_running", persisted.get("running", False))
        )
        self._last_report_at: datetime | None = None
        self._session_room: str | None = None
        self._session_started_at: datetime | None = None
        self._resume_gap_seconds: float | None = None
        self._resume_note: str = ""
        self._last_error: str = ""
        self._consecutive_failures: int = 0
        # 一轮读取要几十秒，手动「立即读取」和定时轮询同时跑会抢 CDP 连接、
        # 互相卡死（实测能卡 10 分钟以上）。这里用锁串起来。
        self._tick_lock = asyncio.Lock()
        if persisted.get("last_report_at"):
            try:
                self._last_report_at = datetime.fromisoformat(
                    str(persisted["last_report_at"])
                )
            except ValueError:
                self._last_report_at = None
        if persisted.get("room_name"):
            self._session_room = str(persisted["room_name"])
        if persisted.get("live_started_at"):
            try:
                self._session_started_at = datetime.fromisoformat(
                    str(persisted["live_started_at"])
                )
            except ValueError:
                self._session_started_at = None
        last_tick = persisted.get("last_tick_at") or persisted.get("heartbeat")
        if last_tick:
            try:
                gap = (
                    datetime.now(UTC)
                    - datetime.fromisoformat(str(last_tick))
                ).total_seconds()
                if gap >= self.interval_seconds:
                    self._resume_gap_seconds = gap
            except ValueError:
                self._resume_gap_seconds = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def roi_target(self) -> float | None:
        provider = self.plan_provider
        if provider is None:
            return None
        try:
            plan = provider()
        except Exception:  # noqa: BLE001
            return None
        value = getattr(plan, "roi_goal", None)
        return float(value) if value else None

    # --- 运行状态持久化（后端重启后能自动恢复盯盘） -------------------------
    def _write_state(self, running: bool) -> None:
        """把「想不想跑 + 跑到哪儿了」落盘，供重启/开机后恢复。"""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now(UTC)
            payload = {
                "running": running,
                "desired_running": self.desired_running,
                "heartbeat": now.isoformat(),
                "last_tick_at": (self._last_run or now).isoformat(),
                "last_report_at": (
                    self._last_report_at.isoformat() if self._last_report_at else None
                ),
                "room_name": self._session_room,
                "live_started_at": (
                    self._session_started_at.isoformat()
                    if self._session_started_at
                    else None
                ),
                "tick_count": self._tick_count,
            }
            self.state_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            return

    def _read_state(self) -> dict:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    async def heartbeat(self) -> dict:
        """前端盯盘窗口打开时每 10 秒调用一次。

        只有「用户想要它跑」时才自动拉起来；用户点过「停止盯盘」后，
        心跳不会再偷偷把它开起来。
        """
        if not self.running and self.desired_running:
            await self.start()
        return self.status()

    async def resume_if_needed(self) -> None:
        """后端启动时：只要盯盘处于「想要运行」状态就自动恢复，并记录断点。

        盯盘是用户主动开/关的开关，不依赖前端窗口；关窗口、关机、后端重启
        都不算停止，只有点「停止盯盘」才会写 desired_running=false。
        """
        if not self.desired_running:
            return
        self._resume_note = self._gap_note()
        await self.start()

    def _gap_note(self) -> str:
        """断点提示语：告诉用户「从哪儿断的、断多久了」。"""
        gap = self._resume_gap_seconds
        if gap is None or gap < self.interval_seconds:
            return ""
        minutes = int(self._resume_gap_seconds // 60)
        if minutes < 60:
            span = f"{minutes} 分钟"
        else:
            span = f"{minutes // 60} 小时 {minutes % 60} 分钟"
        last = (
            self._last_report_at.astimezone(BEIJING).strftime("%m-%d %H:%M")
            if self._last_report_at
            else "（无历史）"
        )
        room = f"（{self._session_room}）" if self._session_room else ""
        return (
            f"盯盘中断 {span}，上次读到 {last}{room}。"
            "本条是恢复后的第一次读取；中断期间的 5 分钟报无法补生成，"
            "只能从当前时点接着往后盯。"
        )

    def connection_gap(self) -> float | None:
        """离上一次成功读取过去了多久（秒）。"""
        if self._last_run is None:
            return self._resume_gap_seconds
        return (datetime.now(UTC) - self._last_run).total_seconds()

    def status(self) -> dict:
        gap = self.connection_gap()
        return {
            "running": self.running,
            "desired_running": self.desired_running,
            "interrupted": bool(self.desired_running) and not self.running,
            "gap_seconds": gap,
            "last_tick_at": self._last_run.isoformat() if self._last_run else "",
            "last_report_at": (
                self._last_report_at.isoformat() if self._last_report_at else ""
            ),
            "room_name": self._session_room,
            "live_started_at": (
                self._session_started_at.isoformat()
                if self._session_started_at
                else None
            ),
            "interval_seconds": self.interval_seconds,
            "tick_count": self._tick_count,
            "last_run": self._last_run.isoformat() if self._last_run else "",
            "reports": len(self.store.list_logs(limit=500)),
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
            "latest": self.store.latest(),
        }

    async def start(self) -> dict:
        self.desired_running = True
        if self.running:
            self._write_state(True)
            return self.status()
        self._task = asyncio.create_task(self._run())
        self._write_state(True)
        return self.status()

    async def stop(self) -> dict:
        self.desired_running = False
        if self._task is not None:
            self._task.cancel()
            try:
                # 任务可能正卡在 CDP / 子进程调用里，取消不会立刻生效 —— 不能死等
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
            self._task = None
        self._resume_gap_seconds = 0
        self._write_state(False)
        return self.status()

    async def resume(self) -> dict:
        """「恢复盯盘」：接着断点继续跑，并立刻补读一次（不等 5 分钟）。"""
        note = self._gap_note()
        self._resume_note = note
        await self.start()
        report = None
        try:
            report = await self.tick_once()
        except Exception as exc:  # noqa: BLE001
            self._resume_note = note
            status = self.status()
            status["resume_error"] = str(exc)
            return status
        status = self.status()
        status["resumed"] = True
        status["resume_note"] = note
        status["resume_report"] = report.get("id") if isinstance(report, dict) else None
        # 补读这一轮如果判定本场已结束，就立刻停 —— 否则 _run 可能已经进入 5 分钟 sleep，
        # 要等下一轮才看到停止标记（用户看到的就是"直播结束了还在盯盘"）。
        if self._pending_stop_reason:
            reason = self._pending_stop_reason
            self._pending_stop_reason = None
            await self.stop()
            await self._publish_notice(reason)
            status = self.status()
            status["resumed"] = True
            status["resume_note"] = note
            status["stopped_reason"] = reason
        return status

    async def tick_once(self, wait: bool = True) -> dict:
        """读一轮。

        wait=True（定时轮询用）：排队等锁。
        wait=False（手动点「立即读取」用）：正在读就直接返回 busy，不让用户干等。
        """
        if not wait and self._tick_lock.locked():
            return {"busy": True, "message": "正在读取中，请等这一轮结束再点"}
        async with self._tick_lock:
            return await self._tick_once_locked()

    async def _tick_once_locked(self) -> dict:
        if self.roi_target() is None and self.plan_refresher is not None:
            try:
                await self.plan_refresher()
            except Exception:  # noqa: BLE001
                pass
        event = self.monitor_service.tick()
        if hasattr(event, "__await__"):
            event = await event
        history = [log for log in self.store.list_logs(limit=10)][::-1]
        baseline_history = self.store.list_logs(limit=400)[::-1]
        room_name = getattr(event.metrics, "room_name", None)
        # 必须带场次：不带的话 compute_baselines 会退化成"同直播间所有历史"，
        # 上一场（甚至已结束场次的冻结页）的样本会混进来污染基线。
        started_for_baseline = getattr(event, "live_started_at", None)
        baselines = compute_baselines(
            baseline_history,
            room_name=room_name,
            session=(
                started_for_baseline.isoformat()
                if started_for_baseline is not None
                else None
            ),
        )
        plan = None
        if self.plan_provider is not None:
            try:
                plan = self.plan_provider()
            except Exception:  # noqa: BLE001
                plan = None
        split = None
        if self.spend_split_provider is not None:
            started_at = getattr(event, "live_started_at", None)
            try:
                split = await self.spend_split_provider(started_at)
            except TypeError:
                # 兼容不接收场次参数的旧 provider
                try:
                    split = await self.spend_split_provider()
                except Exception:  # noqa: BLE001
                    split = None
            except Exception:  # noqa: BLE001
                split = None
        platform_ops = None
        if self.platform_log_provider is not None:
            try:
                platform_ops = await self.platform_log_provider()
            except Exception:  # noqa: BLE001
                platform_ops = None
        # 数据停滞检测：连续 3 次消耗完全不变 → 场次可能已结束或大屏未刷新
        audit_notes: list[str] = []   # 自检记录（本轮做了什么核对），最后写进报表
        spend_now = float(event.metrics.spend or 0)
        if spend_now > self._last_spend_value + 0.01:
            self._last_spend_value = spend_now
            self._last_spend_growth_at = datetime.now(UTC)
        self._recent_spends.append(spend_now)
        self._recent_spends = self._recent_spends[-5:]
        is_stagnant = False
        # 注意：不能再要求 spend_now > 0 —— 直播结束后大屏经常读到 0，
        # 那样会永远判不出"停滞"，也就永远检测不到本场结束。
        if len(self._recent_spends) >= 3:
            tail = {round(v, 2) for v in self._recent_spends[-3:]}
            if len(tail) == 1:
                self._stagnant_ticks += 1
                is_stagnant = True
            else:
                self._stagnant_ticks = 0
        if is_stagnant and self.snapshot_refresher is not None:
            # 自检：先别急着判"消耗停滞"，真的去刷新一次页面再读，看是不是我们读了缓存
            try:
                fresh = await self.snapshot_refresher()
            except Exception:  # noqa: BLE001
                fresh = None
            if fresh is not None:
                fresh_spend = float(getattr(fresh, "spend", 0) or 0)
                if fresh_spend != spend_now:
                    # 刷新后数值变了 → 是我们读了旧页面，采用刷新后的读数
                    from app.services.analytics import AnalyticsService as _Analytics

                    event.metrics = _Analytics().compute(fresh)
                    spend_now = fresh_spend
                    is_stagnant = False
                    self._stagnant_ticks = 0
                    self._recent_spends[-1] = spend_now
                    event.reason = (
                        f"自检：发现读数未变化，已自动刷新大屏并取到新值"
                        f"（{_money(fresh_spend)}）"
                    )
                else:
                    self._stagnant_ticks += 0  # 保持计数
        if is_stagnant and self.session_state_provider is not None:
            # 刷新也刷不动 → 去投放管理页确认：现在还有没有在播的场次
            try:
                state = await self.session_state_provider()
            except Exception:  # noqa: BLE001
                state = "unknown"
            if state == "not-live":
                event.plan_status = "ended"
                audit_notes.append(
                    "确认本场已结束：消耗连续不动、刷新大屏也没变化，"
                    "投放管理页显示当前没有在播场次 —— 按收场快照处理，"
                    "并会为本场生成复盘"
                )
        # 读失败时 event.live_started_at 会是 None；再回退到"本进程上次成功读到的"
        # 以及"持久化状态里的场次开始时间" —— 否则重启后遇到读失败，
        # 结束判定会因为没有场次开始时间而永远不触发。
        session_started = (
            getattr(event, "live_started_at", None)
            or self._last_live_started
            or self._session_started_at
        )
        # 第二道保险：场次已经跑了很久、且消耗长期不增长 → 认定已结束。
        # 为什么需要：大屏页头经常不渲染"已结束"，投放管理页也可能还挂着上一场的
        # 「直播大屏」入口，导致 session_state 误判成 live。
        # 只对"超过 20 小时且 60 分钟没涨消耗"生效 —— 真正在花钱的超长连播不会被误停。
        if event.plan_status != "ended" and session_started is not None:
            now_utc = datetime.now(UTC)
            started = session_started
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            running_hours = (now_utc - started).total_seconds() / 3600
            # 进程刚重启时还没记录过"消耗增长时间"，就回退到场次开始时间 ——
            # 否则重启后这个兜底永远不触发。
            reference = self._last_spend_growth_at or started
            idle_minutes = (now_utc - reference).total_seconds() / 60
            if running_hours > 20 and idle_minutes > 60:
                event.plan_status = "ended"
                audit_notes.append(
                    f"本场已连续 {running_hours:.1f} 小时、且消耗已 {idle_minutes:.0f} 分钟没有增长"
                    " —— 判定直播已结束（不依赖页面上的「已结束」文案）"
                )
        if event.plan_status == "ended" and session_started is not None:
            session_key = session_started.isoformat()
            if self._ended_handled_for != session_key:
                self._ended_handled_for = session_key
                audit_notes.append(
                    "本场已结束：已生成复盘；**盯盘按你的要求自动停止**，"
                    "下一场开播请在「直播盯盘」里手动开始"
                )
                if self.session_end_handler is not None:
                    try:
                        await self.session_end_handler(
                            getattr(event.metrics, "room_name", None), session_started
                        )
                    except Exception:  # noqa: BLE001
                        pass
        # 幂等：只要本轮仍判定"已结束"，就确保停止标记存在。
        # （第一次设完可能被别的路径消费/清掉，之后 _ended_handled_for 已置位就不再设，
        #  结果就是"检测到结束了、但盯盘一直不停" —— 真实踩过。）
        if event.plan_status == "ended" and session_started is not None:
            self._pending_stop_reason = (
                "本场直播已结束：复盘已生成，盯盘已自动停止。"
                "下一场开播后，请在「直播盯盘」里手动开始。"
            )
        if is_stagnant:
            stale_minutes = self._stagnant_ticks * (self.interval_seconds // 60)
            if event.plan_status == "ended":
                event.reason = (
                    f"本场已结束：消耗停留在 {_money(spend_now)}"
                    f"（连续 {stale_minutes} 分钟无变化，已刷新确认）"
                )
            else:
                event.reason = (
                    f"数据停滞：消耗已连续 {stale_minutes} 分钟没有变化"
                    f"（{_money(spend_now)}）；已自动刷新大屏重新读取，数值仍未变化，"
                    "大概率本场已结束（或计划确实停跑）"
                )
        # 场次自检：读到"换场"时先复读一次确认，别被一次误读带偏
        started = getattr(event, "live_started_at", None)
        if started is not None:
            if self._last_live_started is None:
                self._last_live_started = started
            elif started != self._last_live_started:
                previous = self._last_live_started
                confirmed = True
                if self.snapshot_refresher is not None:
                    try:
                        probe = await self.snapshot_refresher()
                    except Exception:  # noqa: BLE001
                        probe = None
                    probe_started = getattr(probe, "live_started_at", None)
                    if probe_started is not None and probe_started == previous:
                        # 复读还是上一场 → 刚才多半读错了，保持原场次
                        confirmed = False
                        started = previous
                        event.live_started_at = previous
                if confirmed:
                    self._last_live_started = started
                    audit_notes.append(
                        "确认换场：上一场 "
                        + previous.astimezone(BEIJING).strftime("%m-%d %H:%M")
                        + " → 本场 "
                        + started.astimezone(BEIJING).strftime("%m-%d %H:%M")
                        + "（已复读确认）"
                    )
                    if self.hub is not None:
                        await self.hub.publish(
                            {
                                "type": "session_started",
                                "room": getattr(event.metrics, "room_name", ""),
                                "started_at": started.isoformat(),
                            }
                        )
                else:
                    audit_notes.append(
                        "读到疑似换场，复读后确认仍在原场次，已忽略这次抖动"
                    )
        plan_splits = None
        if self.plan_split_provider is not None:
            try:
                plan_splits = await self.plan_split_provider()
            except Exception:  # noqa: BLE001
                plan_splits = None
        # 跨源自检：大屏 vs 素材口径（两套接口，差太多就提示，不是拿它判错）
        board_roi = getattr(event.metrics, "roi", None)
        mat_roi = (split or {}).get("split", {}).get("total_roi")
        if board_roi and mat_roi:
            gap = abs(float(mat_roi) - float(board_roi)) / float(board_roi) * 100
            if gap >= 10:
                audit_notes.append(
                    f"跨源偏差：大屏 ROI {float(board_roi):.2f} vs 素材口径 ROI "
                    f"{float(mat_roi):.2f}（差 {gap:.0f}%，两套接口口径不同，"
                    "以是否同向变化为准，不能互相校验）"
                )
        board_spend = getattr(event.metrics, "spend", None)
        mat_spend = (split or {}).get("total_spend")
        if board_spend and mat_spend and float(board_spend) > 0:
            cover = float(mat_spend) / float(board_spend) * 100
            if cover < 95:
                audit_notes.append(
                    f"口径覆盖：素材口径仅覆盖大屏消耗的 {cover:.0f}%"
                    "（大屏含素材维度之外的消耗；占比类结论的分母是素材口径）"
                )
        # 判断阈值：你在「决策」窗口设的 > 本账户分位 > 通用线
        from app.services.thresholds import resolve_thresholds as _resolve_thresholds

        profile_for_lines = None
        if self.profile_provider is not None:
            try:
                profile_for_lines = self.profile_provider()
            except Exception:  # noqa: BLE001
                profile_for_lines = None
        resolved_lines = _resolve_thresholds(profile_for_lines, baselines)

        report = build_watch_report(
            event,
            history,
            self.roi_target(),
            _recent_operations(),
            plan=plan,
            split=split,
            platform_ops=platform_ops,
            baselines=baselines,
            plan_splits=plan_splits,
            stagnant=is_stagnant,
            stagnant_note=getattr(event, "reason", ""),
            resume_note=self._resume_note,
            audit_notes=audit_notes,
            threshold_lines=resolved_lines,
        )
        # 历史账本回流：把本账户实测的操作净效应附在报表里
        try:
            ledger = self._ledger()
        except Exception:  # noqa: BLE001
            ledger = []
        if ledger:
            report["ledger"] = ledger
            extra = ["", "### 历史账本（本账户实测）", ""]
            labels = {"positive": "正向", "negative": "负向", "neutral": "中性"}
            for row in ledger:
                extra.append(
                    f"- {row.get('operation')}：净效应 {float(row.get('net_effect') or 0):+.2f}"
                    f"（n={row.get('n')}，{labels.get(str(row.get('verdict')), row.get('verdict'))}）"
                )
            extra.append("")
            extra.append(
                "> 已扣掉账户自然漂移；样本 < 20 不出结论；"
                "这是**观察到相关**，不是因果，做决策时请结合当下判断。"
            )
            report["report_markdown"] = (
                str(report.get("report_markdown") or "") + "\n".join(extra)
            )
        self.store.append(report)
        self._last_run = datetime.now(UTC)
        self._last_report_at = self._last_run
        self._session_room = report.get("room_name") or self._session_room
        started_now = getattr(event, "live_started_at", None)
        if started_now is not None:
            self._session_started_at = started_now
        self._tick_count += 1
        await self._maybe_alert(report, event, is_stagnant)
        self._resume_gap_seconds = 0
        self._resume_note = ""
        if report.get("source") != "cdp-error":
            self._last_error = ""
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            self._last_error = str(
                report.get("note") or "CDP 读取失败（调试浏览器可能被关了）"
            )
        self._write_state(True)
        if self.hub is not None:
            await self.hub.publish(
                {
                    "type": "live_watch",
                    "id": report["id"],
                    "message": report["report_markdown"],
                    "created_at": report["created_at"],
                }
            )
        return report

    def _alert_context(self) -> str:
        """告警里带上"当前处在什么状态"，不然只看到一句报错没法判断。"""
        bits = []
        if self._session_room:
            bits.append(f"直播间 {self._session_room}")
        if self._session_started_at:
            try:
                bits.append(
                    "本场 "
                    + self._session_started_at.astimezone(BEIJING).strftime("%m-%d %H:%M")
                    + " 开播"
                )
            except Exception:  # noqa: BLE001
                pass
        if self._last_report_at:
            try:
                bits.append(
                    "最后一次成功读数 "
                    + self._last_report_at.astimezone(BEIJING).strftime("%H:%M")
                )
            except Exception:  # noqa: BLE001
                pass
        else:
            bits.append("本进程还没成功读到过数据")
        if self._consecutive_failures:
            bits.append(f"已连续失败 {self._consecutive_failures} 轮")
        return "｜".join(bits)

    def _alert_text(self, condition: str, report: dict, event) -> tuple[str, str]:
        room = report.get("room_name") or self._session_room or "直播间"
        note = str(report.get("note") or getattr(event, "reason", "") or "")
        context = self._alert_context()
        if condition == "cdp-error":
            return (
                f"⚠️ 盯盘读不到数据（{room}）",
                f"- 当前状态：{context}\n"
                f"- 原因：{note or 'CDP 读取失败'}\n"
                "- 影响：这期间不会出报表，也不会判断问题\n"
                "- 怎么修：打开工具 → 直播盯盘 → 点「连接数据源」，"
                "成功后再点「恢复盯盘」；如果提示要登录千川，在弹出的窗口登录一次",
            )
        return (
            f"⚠️ 盯盘数据不动了（{room}）",
            f"- 当前状态：{context}\n"
            f"- 现象：连续多轮消耗没有变化（{note or '数据停滞'}）\n"
            "- 可能：① 这一场已结束，页面冻结在收场快照 ② 大屏没刷新 ③ 计划真的没在跑\n"
            "- 怎么修：先看直播是否已结束；没结束就点「立即读取一次」，"
            "还不动就去千川大屏手动点一次「刷新数据」",
        )

    async def _maybe_alert(self, report: dict, event, stagnant: bool) -> None:
        condition = None
        if report.get("source") == "cdp-error":
            condition = "cdp-error"
        elif stagnant:
            condition = "stagnant"
        now = datetime.now(UTC)
        if condition is None:
            # 恢复正常 → 重置，下次出问题立刻报
            self._alerted_for = None
            self._alerted_at = None
            return
        if self.alert_notifier is None:
            return
        if condition == self._alerted_for and self._alerted_at is not None:
            elapsed = (now - self._alerted_at).total_seconds()
            if elapsed < self.alert_repeat_seconds:
                return  # 同类问题，还没到重复提醒的时间
        self._alerted_for = condition
        self._alerted_at = now
        title, body = self._alert_text(condition, report, event)
        try:
            await self.alert_notifier(title, body)
        except Exception:  # noqa: BLE001
            pass

    async def _maybe_reconnect_cdp(self) -> None:
        """读不到数据且连续失败到阈值时，自己把调试浏览器拉起来重连。

        不是每轮都试（会连开一堆窗口），有冷却时间；连上了就重置失败计数。
        """
        if self.cdp_reconnector is None:
            return
        if self._consecutive_failures < self.reconnect_after_failures:
            return
        now = datetime.now(UTC)
        if (
            self._last_reconnect_at is not None
            and (now - self._last_reconnect_at).total_seconds()
            < self.reconnect_cooldown_seconds
        ):
            return
        self._last_reconnect_at = now
        try:
            result = await self.cdp_reconnector()
        except Exception as exc:  # noqa: BLE001
            await self._publish_notice(
                f"数据源自动重连失败：{type(exc).__name__}: {exc}，稍后会再试"
            )
            return
        if not (isinstance(result, dict) and result.get("connected")):
            return  # 没连上：保持静默，让常规告警去提醒（避免刷屏）
        self._consecutive_failures = 0
        self._last_error = ""
        if result.get("needs_login"):
            await self._publish_notice(
                "数据源（调试浏览器）已自动重连，但浏览器还没登录千川："
                "请在弹出的窗口登录一次，登录后点「恢复盯盘」。"
            )
        else:
            await self._publish_notice(
                "数据源（调试浏览器）断开后已自动重连，盯盘继续。"
            )

    def _ledger(self) -> list[dict]:
        """历史账本（本账户实测的操作净效应），缓存 30 分钟。

        让每份盯盘报表都带上"这类操作历史上到底有没有用"。
        """
        now = datetime.now(UTC)
        cached = getattr(self, "_ledger_cache", None)
        if cached is not None and (now - cached[0]).total_seconds() < 1800:
            return cached[1]
        rows: list[dict] = []
        try:
            from app.services.ops_outcome import compute_ops_outcome

            result = compute_ops_outcome(self.store.list_logs(limit=1500))
            rows = [
                row
                for row in result.get("operations", [])
                if int(row.get("n") or 0) >= int(result.get("min_sample") or 20)
            ]
        except Exception:  # noqa: BLE001
            rows = []
        self._ledger_cache = (now, rows)
        return rows

    async def _run(self) -> None:
        while True:
            try:
                # 整体超时：一轮读几个页面，任何一个 await 卡住都会把整个循环拖死
                # （实测卡过 10 分钟以上，界面还显示"运行中"）。超时就中断这轮。
                await asyncio.wait_for(
                    self.tick_once(), timeout=self.tick_timeout_seconds
                )
            except asyncio.TimeoutError:
                self._last_error = (
                    f"本轮读取超时（>{self.tick_timeout_seconds:.0f} 秒），"
                    "已中断这一轮，下一轮继续"
                )
                self._consecutive_failures += 1
                await self._publish_notice(self._last_error)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # 读不到数据（多半是调试浏览器被关了）——记下来给前端提示，
                # 但不要退出循环，等数据源恢复后下一轮自动接上。
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._consecutive_failures += 1
            await self._maybe_reconnect_cdp()
            if self._pending_stop_reason:
                # 本场已结束：出完复盘就收工，下一场要手动开
                reason = self._pending_stop_reason
                self._pending_stop_reason = None
                self.desired_running = False
                self._write_state(False)
                await self._publish_notice(reason)
                return
            await asyncio.sleep(self.interval_seconds)

    async def _publish_notice(self, text: str) -> None:
        if self.hub is None:
            return
        try:
            await self.hub.publish(
                {"type": "live_watch_notice", "message": text}
            )
        except Exception:  # noqa: BLE001
            pass
