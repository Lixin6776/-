from datetime import UTC, datetime

from app.services.action_planner import PlanSnapshot
from app.services.monitor import MonitorEvent

MISSING = "暂无法读取"


def _money(value: float | None) -> str:
    if value is None:
        return MISSING
    return f"¥{value:,.2f}"


def _number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return MISSING
    return f"{value:.{digits}f}"


def _spend_trend(monitor: MonitorEvent | None) -> str:
    if monitor is None or monitor.spend_delta is None:
        return "暂无法判断"
    if monitor.spend_delta > 0:
        return "持续"
    if monitor.spend_delta < 0:
        return "放缓"
    return "不动"


def format_strategy_card(
    plan: PlanSnapshot | None,
    monitor: MonitorEvent | None,
    read_at: datetime | None = None,
) -> str:
    timestamp = read_at or (monitor.captured_at if monitor is not None else datetime.now(UTC))
    plan_name = plan.name if plan is not None else MISSING
    account_name = plan.account_name if plan is not None and plan.account_name else MISSING
    today_spend = monitor.metrics.spend if monitor is not None else None
    period_spend = monitor.spend_delta if monitor is not None else None
    minutes = monitor.minutes_since_previous if monitor is not None else None
    budget = plan.budget if plan is not None and plan.budget > 0 else None
    target_roi = plan.roi_goal if plan is not None else None
    payment_roi = monitor.metrics.roi if monitor is not None else None
    minutes_text = MISSING if minutes is None else f"{minutes:.0f}"
    return f"""### 全域投放策略卡｜{timestamp.astimezone().strftime("%Y-%m-%d %H:%M")}

**计划：{plan_name}**

- 账户：{account_name}
- 今日累计消耗：{_money(today_spend)}
- 本周期消耗：{_money(period_spend)}（距上次读取 {minutes_text} 分钟）
- 计划预算：{_money(budget)}
- 目标ROI：{_number(target_roi)}
- 支付ROI：{_number(payment_roi)}
- 净成交ROI（1小时）：{MISSING}
- 消耗趋势：{_spend_trend(monitor)}"""
