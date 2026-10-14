# -*- coding: utf-8 -*-
"""判断阈值：优先用你在「决策」窗口设定的值，其次账户分位数，最后通用参考线。

优先级（高 → 低）：
  1. custom    你在「决策」窗口填的 —— 最贴你的打法，新号也能用
  2. baseline  本账户近 N 次采样的分位 —— 有历史就用你自己的水平
  3. default   通用参考线 —— 兜底，报表里必须标注"非本账户"

为什么要分三层：通用值对新号不成立（没有历史就无所谓"分位"），
而行业/对标数据又拿不到（千川诊断模块目前读不到）。所以让用户能自己定，
系统只负责"如实说明这条线是谁定的"。
"""

DEFAULT_THRESHOLDS = {
    "exposure_view_rate": 4.0,   # 曝光观看率（%）
    "view_conversion_rate": 5.0,  # 观看成交转化率（%）
    "gpm": 3500.0,               # GPM（元）
    "cpm": 100.0,                # CPM（元）
    "assist_share": 50.0,        # 追投/调控占比（%），官方建议约 25%
}

# 哪个方向算"不好"：high = 越高越差（成本类），low = 越低越差
DIRECTIONS = {"cpm": "high", "assist_share": "high"}

NAMES = {
    "exposure_view_rate": "曝光观看率",
    "view_conversion_rate": "观看成交转化率",
    "gpm": "GPM",
    "cpm": "CPM",
    "assist_share": "追投/调控占比",
}

UNITS = {
    "exposure_view_rate": "%",
    "view_conversion_rate": "%",
    "gpm": " 元",
    "cpm": " 元",
    "assist_share": "%",
}

SOURCE_LABEL = {
    "custom": "你在决策窗口设定的值",
    "baseline": "本账户历史分位",
    "default": "通用参考线（非本账户，仅兜底）",
}


def custom_thresholds(profile) -> dict:
    """从投放策略里取出你设的阈值（存在 hard_constraints.thresholds）。"""
    constraints = getattr(profile, "hard_constraints", None)
    if isinstance(constraints, dict):
        raw = constraints.get("thresholds")
        if isinstance(raw, dict):
            return raw
    return {}


def resolve_thresholds(profile=None, baselines: dict | None = None) -> dict[str, dict]:
    """算出每个指标"当前生效的判断线"以及它的来源。"""
    custom = custom_thresholds(profile)
    out: dict[str, dict] = {}
    for key, default in DEFAULT_THRESHOLDS.items():
        direction = DIRECTIONS.get(key, "low")
        value: float | None = None
        source = "default"
        custom_value = custom.get(key)
        if isinstance(custom_value, (int, float)) and not isinstance(custom_value, bool):
            value, source = float(custom_value), "custom"
        else:
            info = (baselines or {}).get(key) or {}
            if info.get("samples"):
                candidate = info.get("high") if direction == "high" else info.get("low")
                if candidate is not None:
                    value, source = float(candidate), "baseline"
        if value is None:
            value = float(default)
        out[key] = {
            "key": key,
            "name": NAMES[key],
            "value": value,
            "unit": UNITS[key],
            "direction": direction,
            "source": source,
            "samples": int(((baselines or {}).get(key) or {}).get("samples") or 0),
        }
    return out


def describe(entry: dict) -> str:
    """给报表用的「依据」文案 —— 必须写清楚这条线是谁定的。"""
    if not entry:
        return "参考线"
    label = SOURCE_LABEL.get(str(entry.get("source")), "参考线")
    return f"{entry['name']} {float(entry['value']):,.2f}{entry.get('unit', '')}（{label}）"


def value_of(lines: dict | None, key: str, fallback: float) -> float:
    entry = (lines or {}).get(key)
    try:
        return float(entry["value"]) if entry else float(fallback)
    except (KeyError, TypeError, ValueError):
        return float(fallback)


def text_of(lines: dict | None, key: str, fallback: float, fallback_unit: str) -> str:
    """没有解析结果时，也要如实说是"通用参考线"。"""
    entry = (lines or {}).get(key)
    if entry:
        return describe(entry)
    return f"通用参考线 {fallback:g}{fallback_unit}（本账户样本不足，非你的水平）"
