"""盯盘 / 复盘输出前的自检。

目的：每条结论都要能对上数据，数据本身要自洽，不把错的、缺的、矛盾的
东西直接发给用户。
"""

from __future__ import annotations

REQUIRED_METRICS = ("roi", "spend", "gmv", "orders", "gpm", "online_viewers")


def _num(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def check_metrics(metrics, split: dict | None = None) -> list[str]:
    """数据自检：完整性 + 口径一致性 + 异常值。返回问题列表（空=通过）。"""
    issues: list[str] = []

    # 1) 完整性
    missing = [k for k in REQUIRED_METRICS if _num(getattr(metrics, k, None)) is None]
    if missing:
        issues.append(f"缺少核心指标：{', '.join(missing)}")

    roi = _num(getattr(metrics, "roi", None))
    spend = _num(getattr(metrics, "spend", None))
    gmv = _num(getattr(metrics, "gmv", None))
    gpm = _num(getattr(metrics, "gpm", None))
    views = _num(getattr(metrics, "views", None))

    # 2) ROI = 成交 / 消耗
    if roi and spend and gmv and spend > 0:
        calc = gmv / spend
        if abs(calc - roi) / max(roi, 0.01) > 0.05:
            issues.append(
                f"ROI 口径不一致：页面 {roi:.2f}，按成交/消耗算是 {calc:.2f}"
            )

    # 3) GPM 不做公式校验
    #    实测：大屏 GPM 无法用 GMV/千次观看(人数或次数) 复现，
    #    千川内部口径不公开。这里以页面值为准，不做反算断言。
    # 3.5) 漏斗单调性：曝光 ≥ 观看次数 ≥ 商品点击 ≥ 成交订单
    # 注意：商品点击「次数」可以大于观看「次数」（一人可点多个商品），
    # 所以只校验 曝光 ≥ 观看次数 ≥ 成交订单数 这两段硬关系。
    funnel = [
        ("曝光次数", _num(getattr(metrics, "exposure_count", None))),
        ("观看次数", _num(getattr(metrics, "view_count", None))),
        ("成交订单数", _num(getattr(metrics, "orders", None))),
    ]
    present = [(name, v) for name, v in funnel if v is not None]
    for (n1, v1), (n2, v2) in zip(present, present[1:]):
        if v1 < v2:
            issues.append(
                f"漏斗数据不成立：{n1} {v1:,.0f} < {n2} {v2:,.0f}"
                "（上游不可能小于下游，多半是解析单位出错，如把「112万」读成 112）"
            )

    # 4) 消耗结构
    if split:
        basic = _num(split.get("basic_spend")) or 0.0
        assist = _num(split.get("assist_spend")) or 0.0
        total = _num(split.get("total_spend")) or 0.0
        s = basic + assist
        if total > 0 and s < total * 0.8:
            issues.append(
                f"消耗结构对不上：基础+追投 ¥{s:,.0f}，素材口径整体 ¥{total:,.0f}"
                f"（差 {100 - s / total * 100:.0f}%，可能是旧版追投或其他口径）"
            )

    # 5) 异常值
    if spend is not None and spend < 0:
        issues.append("消耗为负，数据异常")
    if roi is not None and roi == 0 and spend and spend > 0:
        issues.append("有消耗但 ROI 为 0，可能是数据未回传")

    return issues


CONCLUSION_WORDS = ("偏", "低", "高", "停滞", "加快", "未达标", "下降", "回升", "不足")


def check_conclusions(problems: list[str]) -> list[str]:
    """结论自检：出现判断性表述时，必须带「依据」。"""
    issues: list[str] = []
    for item in problems:
        if "依据" in item or "目标" in item:
            continue
        # 带前后对比（1.89 → 1.91）的结论，本身就算依据
        if "→" in item:
            continue
        if any(word in item for word in CONCLUSION_WORDS):
            issues.append(f"结论缺少依据：{item[:40]}…")
    return issues


def self_check(metrics, problems: list[str], split: dict | None = None) -> list[str]:
    return check_metrics(metrics, split) + check_conclusions(problems)


def render_self_check(issues: list[str], audit_notes: list[str] | None = None) -> str:
    """issues=必须确认的问题；audit_notes=自检过程中做了什么（刷新/复读/跨源对照）。"""
    notes = [n for n in (audit_notes or []) if n]
    if not issues:
        lines = ["### 自检", "", "- ✅ 通过：核心指标完整、口径一致、每条结论都有依据"]
        lines.extend(f"- 🔎 {note}" for note in notes)
        return "\n".join(lines) + "\n"
    lines = ["### 自检", "", f"- ⚠️ 发现 {len(issues)} 个需要确认的问题："]
    lines.extend(f"  - {item}" for item in issues)
    lines.append("- 以上问题可能影响判断，请先核对数据再看结论")
    lines.extend(f"- 🔎 {note}" for note in notes)
    return "\n".join(lines) + "\n"

# 各指标的合理区间（超出即判为解析错误，需要先核对数据）
SANITY_RANGES = {
    "cpm": (5.0, 2000.0, "CPM"),
    "gpm": (10.0, 50000.0, "GPM"),
    "roi": (0.05, 50.0, "ROI"),
    "exposure_view_rate": (0.05, 60.0, "曝光观看率"),
    "view_conversion_rate": (0.01, 60.0, "观看成交转化率"),
}


def check_ranges(metrics) -> list[str]:
    """区间合理性：超出物理可能的范围，说明解析出错。"""
    issues: list[str] = []
    for field, (low, high, label) in SANITY_RANGES.items():
        value = _num(getattr(metrics, field, None))
        if value is None:
            continue
        if value < low or value > high:
            issues.append(
                f"{label} 数值异常：{value:,.2f}（合理区间 {low}~{high}），"
                "多半是解析错误（如大屏「万」单位没还原）"
            )
    return issues


def check_split(split: dict | None, metrics=None) -> list[str]:
    """消耗结构对账：基础 + 追投 应接近素材口径整体。"""
    issues: list[str] = []
    if not split:
        return issues
    basic = _num(split.get("basic_spend")) or 0.0
    assist = _num(split.get("assist_spend")) or 0.0
    total = _num(split.get("total_spend")) or 0.0
    if total <= 0:
        return issues
    covered = basic + assist
    if covered < total * 0.8:
        issues.append(
            f"消耗结构对不上：基础+追投 ¥{covered:,.0f} 只占素材口径整体 ¥{total:,.0f} 的 "
            f"{covered / total * 100:.0f}%（正常应 ≥80%）"
        )
    if basic > total * 1.05 or assist > total * 1.05:
        issues.append(
            f"消耗结构异常：基础 ¥{basic:,.0f} / 追投 ¥{assist:,.0f} 超过整体 ¥{total:,.0f}"
        )
    return issues


def check_plan_splits(splits: list[dict] | None) -> list[str]:
    """基础 vs 整体拆分校验：基础消耗不能大于整体消耗，ROI 不能为负。"""
    issues: list[str] = []
    for item in splits or []:
        room = str(item.get("room") or "")[:16]
        overall = _num(item.get("roi"))
        base = _num(item.get("base_roi"))
        spend = _num(item.get("spend"))
        base_spend = _num(item.get("base_spend"))
        # 已暂停/未开播的计划 ROI 为 0 是正常的，只有「有消耗但 ROI ≤ 0」才算异常
        if (
            overall is not None
            and base is not None
            and (overall <= 0 or base <= 0)
            and (spend or 0) > 0
            and (base_spend or 0) > 0
        ):
            issues.append(f"{room} 有消耗但 ROI ≤ 0，数据异常")
        if spend is not None and base_spend is not None and base_spend > spend * 1.05:
            issues.append(
                f"{room} 基础消耗 ¥{base_spend:,.0f} 大于整体消耗 ¥{spend:,.0f}，数据不成立"
            )
    return issues


def verify_data(metrics, split=None, plan_splits=None) -> tuple[bool, list[str]]:
    """分析前的硬门槛：全部通过才允许出分析结论。"""
    issues: list[str] = []
    issues += check_metrics(metrics, split)
    issues += check_ranges(metrics)
    issues += check_split(split, metrics)
    issues += check_plan_splits(plan_splits)
    return (len(issues) == 0), issues
