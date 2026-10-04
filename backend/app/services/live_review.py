import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.services.analytics import ComputedMetrics
from app.services.monitor import MonitorProfile

REVIEW_PATH = Path(__file__).resolve().parents[3] / ".local" / "live_reviews.json"


def _money(value: float | None) -> str:
    return "--" if value is None else f"¥{value:,.2f}"


def _ratio(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}"


def build_live_review(
    snapshot: MetricSnapshot,
    metrics: ComputedMetrics,
    profile: MonitorProfile,
    captured_at: datetime | None = None,
) -> dict:
    ended_at = captured_at or snapshot.captured_at
    roi_target = profile.hard_constraints.get("roi_target")
    target = float(roi_target) if isinstance(roi_target, (int, float)) else None
    roi_met = None if target is None or metrics.roi is None else metrics.roi >= target

    diagnosis = []
    if target is None:
        diagnosis.append("未配置目标ROI，本次只能记录结果，无法判断是否达标。")
    elif metrics.roi is not None and metrics.roi < target:
        diagnosis.append(
            f"综合营销 ROI 为 {metrics.roi:.2f}，低于目标 {target:.2f}。"
        )
    if metrics.orders == 0:
        diagnosis.append("本场没有成交订单，需要检查流量精准度、商品承接和直播转化。")
    if metrics.online_viewers < 10:
        diagnosis.append("结束时在线人数较低，需关注直播间停留和后续流量承接。")
    if not diagnosis:
        diagnosis.append("核心指标未发现明显异常，可按当前方向继续观察。")

    if target is None:
        tomorrow = [
            "先补齐投放策略、目标 ROI 和预算约束，再决定明日是否放量。",
            "保持当前预算和出价不变，先观察一个完整直播周期，不做自动调整。",
            "继续按 5–10 分钟监控 ROI、消耗、成交和在线人数，确认数据口径一致。",
        ]
    elif roi_met:
        tomorrow = [
            "保持当前 ROI 目标和基础预算，先在早场小幅放量验证流量质量。",
            "优先复用本场高转化素材和时段，放量幅度建议控制在 10%–20%。",
            "继续按 5–10 分钟监控 ROI、消耗、成交和在线人数，出现连续下滑再暂停放量。",
        ]
    else:
        tomorrow = [
            "先不直接扩大预算，优先检查低 ROI 时段的消耗和成交结构。",
            "将明日预算集中到高转化时段，低效时段降低预算或暂停。",
            "如需调低出价，建议先控制在 5%–10%，观察一个完整数据周期后再继续调整。",
            "优先使用已有高转化素材，不新增素材上传；素材绑定或替换必须人工确认。",
        ]

    review_time = snapshot.live_started_at or ended_at
    date_text = review_time.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    result_text = "未配置" if target is None else ("无法判断" if roi_met is None else ("达标" if roi_met else "未达标"))
    report = f"""## 直播复盘｜{date_text}

### 一、核心结果

- 综合成本：{_money(metrics.spend)}
- 综合营销 ROI：{_ratio(metrics.roi)}
- 净成交金额：{_money(metrics.gmv)}
- 整体成交订单数：{metrics.orders}
- GPM：{_money(metrics.gpm)}
- 直播间整体观看人数：{snapshot.views}
- 实时在线人数：{metrics.online_viewers}

### 二、结果判断

- 当前投放策略：{profile.business_direction}
- 主目标：{profile.primary_objective}
- ROI 目标：{_ratio(target)}
- 是否达标：{result_text}

### 三、问题诊断

{chr(10).join(f"- {item}" for item in diagnosis)}

### 四、明日投放策略

{chr(10).join(f"- {item}" for item in tomorrow)}

> 以上均为只读分析建议，任何预算、出价、定向或素材调整都必须先经过人工确认。"""
    return {
        "id": str(uuid.uuid4()),
        "date": date_text,
        "created_at": datetime.now(UTC).isoformat(),
        "ended_at": ended_at.isoformat(),
        "plan_id": None,
        "report_markdown": report,
        "metrics": metrics.model_dump(mode="json"),
    }


class LiveReviewStore:
    def __init__(self, path: Path = REVIEW_PATH) -> None:
        self.path = path

    def list_reviews(self) -> list[dict]:
        return self._read()

    def latest(self) -> dict | None:
        items = self._read()
        return items[0] if items else None

    def add_if_absent(self, review: dict) -> dict:
        items = self._read()
        if any(item.get("date") == review.get("date") for item in items):
            return next(item for item in items if item.get("date") == review["date"])
        items.append(review)
        self._write(items)
        return review

    def _read(self) -> list[dict]:
        import json

        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def _write(self, items: list[dict]) -> None:
        import json

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
