import inspect
import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.services.action_planner import PlanSnapshot
from app.services.monitor import MonitorEvent

MATERIAL_ANALYSIS_PATH = (
    Path(__file__).resolve().parents[3] / ".local" / "material_analyses.json"
)


class MaterialMetric(BaseModel):
    material_id: str
    name: str
    spend: float = 0.0
    roi: float | None = None
    gmv: float = 0.0
    orders: int = 0
    order_cost: float | None = None
    ctr: float | None = None
    conversion_rate: float | None = None
    created_at: str = ""
    tags: tuple[str, ...] = Field(default_factory=tuple)


def _currency(value: float | None) -> str:
    return "--" if value is None else f"¥{value:,.2f}"


def _ratio(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}"


def _percentage(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}%"


def _safe_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _short_name(value: str, limit: int = 42) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _generic_directions(roi_met: bool | None) -> tuple[str, list[str]]:
    if roi_met is None:
        return (
            "尚未读取到 ROI 目标，先按通用优化方向生成素材建议。",
            [
                "保持商品和落地页不变，按痛点、效果、信任感各制作 2 条素材做并行测试。",
                "前 3 秒直接展示用户问题和产品使用场景，减少泛品牌介绍。",
                "增加真人实测、直播现场演示和用户评价，提升停留与转化。",
                "统一素材变量，只改变开场和表达方式，方便后续判断哪类内容更有效。",
            ],
        )
    if roi_met:
        return (
            "整体 ROI 达到目标，优先复制有效素材结构并做小幅变体。",
            [
                "复刻当前高 ROI 素材的前 3 秒钩子，保持同一产品卖点和表达节奏。",
                "围绕高转化素材制作 3–5 条变体，只替换开场画面、口播顺序或字幕样式。",
                "增加真实使用场景和直播切片，优先保留能直接说明产品效果的内容。",
                "保持新素材与原素材的商品、定向和落地页一致，避免同时更换多个变量。",
            ],
        )
    return (
        "整体 ROI 未达到目标，新素材应减少泛化卖点，强化直接转化理由。",
        [
            "减少纯价格促销和泛流量表达，改为痛点、效果演示、真实反馈三类方向。",
            "前 3 秒直接展示用户问题和使用前后对比，避免长铺垫和重复品牌介绍。",
            "增加真人实测、直播现场演示和用户评价截图，强化停留与转化。",
            "按痛点、效果、信任感各制作 2 条素材，统一商品和落地页，方便后续对比。",
        ],
    )


def _material_table(materials: list[MaterialMetric]) -> str:
    lines = [
        "| 素材 | 消耗 | 综合ROI | 成交金额 | 订单 | 转化率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in materials[:8]:
        lines.append(
            f"| {_safe_cell(_short_name(item.name))} | {_currency(item.spend)} | "
            f"{_ratio(item.roi)} | {_currency(item.gmv)} | {item.orders} | "
            f"{_percentage(item.conversion_rate)} |"
        )
    return "\n".join(lines)


def _material_analysis(
    materials: list[MaterialMetric],
    roi_target: float | None,
) -> tuple[str, str, str, list[str]]:
    spent = [item for item in materials if item.spend > 0]
    spent.sort(key=lambda item: item.spend, reverse=True)
    total_spend = sum(item.spend for item in spent)
    high_spend_cutoff = max(500.0, total_spend * 0.05)
    winners = [
        item
        for item in spent
        if roi_target is not None and item.roi is not None and item.roi >= roi_target
    ]
    losers = [
        item
        for item in spent
        if roi_target is not None
        and item.roi is not None
        and item.roi < roi_target * 0.8
        and item.spend >= high_spend_cutoff
    ]

    assessment = (
        f"本周期读取到 {len(materials)} 条素材，合计消耗 {_currency(total_spend)}；"
        f"其中 {len(winners)} 条达到目标ROI，{len(losers)} 条属于高消耗低效素材。"
    )
    winner_lines = [
        f"- {_short_name(item.name)}：消耗 {_currency(item.spend)}，综合ROI {_ratio(item.roi)}，"
        f"成交 {_currency(item.gmv)}，订单 {item.orders}。"
        for item in winners[:3]
    ]
    loser_lines = [
        f"- {_short_name(item.name)}：消耗 {_currency(item.spend)}，综合ROI {_ratio(item.roi)}，"
        f"订单成本 {_currency(item.order_cost)}。"
        for item in losers[:3]
    ]
    if not winner_lines:
        winner_lines = ["- 本周期没有素材达到当前目标ROI，不建议直接复制现有爆量结构。"]
    if not loser_lines:
        loser_lines = ["- 暂无满足“高消耗且低于目标ROI 80%”条件的素材。"]

    directions: list[str] = []
    if winners:
        best = winners[0]
        directions.append(
            f"优先复刻「{_short_name(best.name)}」：其综合ROI {_ratio(best.roi)}，"
            f"消耗 {_currency(best.spend)}，测试同钩子、同卖点的 3–5 条变体。"
        )
        tags = [tag for item in winners[:3] for tag in item.tags]
        if tags:
            directions.append(
                "保留高效素材的内容标签（"
                + "、".join(dict.fromkeys(tags))
                + "），只替换开场画面、口播顺序或字幕样式。"
            )
    else:
        directions.append("暂停复制现有低ROI结构，改用痛点、效果演示、真实反馈三类方向重做素材。")
    if losers:
        directions.append(
            "对「"
            + "」「".join(_short_name(item.name, 24) for item in losers[:2])
            + "」先减少预算测试量，再做新的开场和卖点版本，任何减停操作都需要人工确认。"
        )
    directions.extend(
        [
            "前 3 秒直接展示用户问题和产品使用场景，减少泛品牌介绍。",
            "新素材一次只改一个主要变量，并保持商品、定向和落地页一致，方便比较。",
        ]
    )
    return assessment, "\n".join(winner_lines), "\n".join(loser_lines), directions


def build_material_analysis(
    plan: PlanSnapshot | None,
    event: MonitorEvent | None,
    generated_at: datetime | None = None,
    materials: list[MaterialMetric] | None = None,
    report_date: date | None = None,
    materials_error: str | None = None,
) -> dict:
    now = generated_at or datetime.now(UTC)
    analysis_date = report_date or now.astimezone().date()
    metrics = event.metrics if event is not None else None
    roi_target = plan.roi_goal if plan is not None else None
    roi = metrics.roi if metrics is not None else plan.roi if plan is not None else None
    roi_met = None if roi_target is None else (roi is not None and roi >= roi_target)

    if materials:
        assessment, winners, losers, directions = _material_analysis(materials, roi_target)
        material_section = "\n\n".join(
            [
                _material_table(materials),
                "#### 高消耗达标素材",
                winners,
                "#### 低效素材",
                losers,
            ]
        )
    else:
        assessment, directions = _generic_directions(roi_met)
        if materials_error:
            detail = f"素材明细读取失败：{materials_error}"
        else:
            detail = "当前页面暂未暴露稳定的素材级明细，本报告先基于直播间整体投放结果生成新素材方向。"
        material_section = (
            f"{detail}\n\n"
            "后续接入素材级数据后会自动细化到单条素材，并按高消耗、达标和低效分层。"
        )

    metrics_payload = metrics.model_dump(mode="json") if metrics is not None else {}
    metrics_payload["material_count"] = len(materials or [])
    report = f"""## 素材分析报告｜{analysis_date.isoformat()}

### 一、投放概况

- 计划：{plan.name if plan is not None else "暂无法读取"}
- 综合成本：{_currency(metrics.spend if metrics is not None else None)}
- 综合营销 ROI：{_ratio(roi)}
- 净成交金额：{_currency(metrics.gmv if metrics is not None else None)}
- 整体成交订单数：{metrics.orders if metrics is not None else "--"}
- GPM：{_currency(metrics.gpm) if metrics is not None and metrics.gpm is not None else "--"}
- 目标ROI：{_ratio(roi_target)}
- 长期策略约束：{event.banner if event is not None else "暂无法读取"}

{assessment}

### 二、逐条素材表现

{material_section}

### 三、新素材制作方向

{chr(10).join(f"- {item}" for item in directions)}

### 四、执行提醒

- 本报告只提供制作方向，不自动上传、替换或绑定素材。
- 素材选择和预算调整属于账户写操作，必须先预览并由用户确认。
- 当前系统保持只读模式，任何自动执行都必须等待明确授权。"""
    return {
        "id": str(uuid.uuid4()),
        "date": analysis_date.isoformat(),
        "created_at": now.isoformat(),
        "report_markdown": report,
        "metrics": metrics_payload,
    }


class MaterialAnalysisStore:
    def __init__(self, path: Path = MATERIAL_ANALYSIS_PATH) -> None:
        self.path = path

    def list_analyses(self) -> list[dict]:
        return self._read()

    def latest(self) -> dict | None:
        items = self._read()
        return items[0] if items else None

    def add_if_absent(self, report: dict) -> dict:
        items = self._read()
        existing_index = next(
            (index for index, item in enumerate(items) if item.get("date") == report.get("date")),
            None,
        )
        if existing_index is not None:
            existing = items[existing_index]
            existing_count = int(existing.get("metrics", {}).get("material_count", 0) or 0)
            new_count = int(report.get("metrics", {}).get("material_count", 0) or 0)
            if new_count <= existing_count:
                return existing
            items[existing_index] = report
            self._write(items)
            return report
        items.append(report)
        self._write(items)
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
        self.path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


async def generate_and_publish_material_analysis(
    monitor_service,
    plan_provider,
    store: MaterialAnalysisStore,
    hub,
    material_reader=None,
    analysis_date: date | None = None,
) -> dict:
    event = monitor_service.latest_event() if hasattr(monitor_service, "latest_event") else None
    if event is None:
        event = monitor_service.tick()
        if inspect.isawaitable(event):
            event = await event
    materials = None
    materials_error = None
    if material_reader is not None and analysis_date is not None:
        try:
            materials = await material_reader.read(analysis_date)
        except Exception as exc:  # noqa: BLE001
            materials_error = str(exc)
    report = store.add_if_absent(
        build_material_analysis(
            plan_provider(),
            event,
            materials=materials,
            report_date=analysis_date,
            materials_error=materials_error,
        )
    )
    await hub.publish(
        {
            "type": "material_analysis",
            "id": report["id"],
            "message": report["report_markdown"],
            "created_at": report["created_at"],
        }
    )
    return report
