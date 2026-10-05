import inspect
import json
import uuid
from datetime import UTC, date, datetime, timedelta
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


def _date_from_text(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace(" ", "T")).date()
    except ValueError:
        return None


def _comparison_table(rows: list[dict]) -> str:
    lines = [
        "| 素材 | 今日消耗 | 昨日消耗 | 消耗变化 | 综合ROI |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        item = row["material"]
        previous_spend = float(row["previous_spend"])
        delta = float(row["delta"])
        if previous_spend <= 0:
            change = f"新增 {_currency(delta)}"
        else:
            change = f"{delta:+,.2f} ({row['change_pct']:+.1f}%)"
        lines.append(
            f"| {_safe_cell(_short_name(item.name))} | {_currency(item.spend)} | "
            f"{_currency(previous_spend)} | {change} | {_ratio(item.roi)} |"
        )
    return "\n".join(lines)


def _new_material_section(
    new_materials: list[MaterialMetric],
    new_material_spend: float,
    total_spend: float,
) -> str:
    if not new_materials:
        return "本日读取范围内没有发现新素材。"
    share = (new_material_spend / total_spend * 100) if total_spend else 0.0
    lines = [
        f"- 新素材上新：{len(new_materials)} 条",
        f"- 新素材消耗：{_currency(new_material_spend)}，占今日素材总消耗 {share:.1f}%",
        "",
        _material_table(new_materials),
    ]
    return "\n".join(lines)


def _material_change_section(
    change_rows: list[dict],
    growth_rows: list[dict],
    decline_rows: list[dict],
    stopped_rows: list[dict],
    has_previous: bool,
) -> str:
    if not has_previous:
        return "未读取到上一日素材数据，今天暂时只生成基础消耗和新素材分析。"
    if not change_rows and not stopped_rows:
        return "今天没有可用于对比的素材消耗变化。"

    def render_rows(rows: list[dict], increase: bool) -> list[str]:
        if not rows:
            return ["- 暂无。"]
        result = []
        for row in rows[:5]:
            item = row["material"]
            delta = float(row["delta"])
            result.append(
                f"- {_short_name(item.name)}：今日 {_currency(item.spend)}，"
                f"昨日 {_currency(float(row['previous_spend']))}，"
                f"变化 {delta:+,.2f}。"
            )
        return result

    sections = []
    if change_rows:
        sections.append(_comparison_table(change_rows[:10]))
    sections.extend(
        [
            "#### 增长素材",
            *render_rows(growth_rows, increase=True),
            "#### 下降素材",
            *render_rows(decline_rows, increase=False),
            "#### 停止消耗素材",
            *(
                [
                    f"- {_short_name(row['material'].name)}：昨日 {_currency(float(row['previous_spend']))}，今日 0，已停止消耗。"
                    for row in stopped_rows[:5]
                ]
                or ["- 暂无。"]
            ),
        ]
    )
    return "\n".join(sections)


def _material_analysis(
    materials: list[MaterialMetric],
    previous_materials: list[MaterialMetric] | None,
    roi_target: float | None,
    analysis_date: date,
) -> tuple[str, str, str, list[str], dict]:
    spent = [item for item in materials if item.spend > 0]
    spent.sort(key=lambda item: item.spend, reverse=True)
    previous_by_id = {item.material_id: item for item in (previous_materials or [])}
    current_by_id = {item.material_id: item for item in materials}
    total_spend = sum(item.spend for item in spent)
    high_spend_cutoff = max(500.0, total_spend * 0.05) if total_spend else 0.0
    running = [item for item in spent if item.spend >= high_spend_cutoff]
    running_spend = sum(item.spend for item in running)

    new_materials = [
        item for item in materials if _date_from_text(item.created_at) == analysis_date
    ]
    new_material_spend = sum(item.spend for item in new_materials)

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

    change_rows: list[dict] = []
    for item in spent:
        previous = previous_by_id.get(item.material_id)
        previous_spend = previous.spend if previous is not None else 0.0
        delta = item.spend - previous_spend
        change_pct = (delta / previous_spend * 100) if previous_spend > 0 else 0.0
        change_rows.append(
            {
                "material": item,
                "previous_spend": previous_spend,
                "delta": delta,
                "change_pct": change_pct,
            }
        )
    change_rows.sort(key=lambda row: abs(float(row["delta"])), reverse=True)
    growth_rows = [
        row for row in change_rows if float(row["delta"]) > 0 and float(row["previous_spend"]) > 0
    ]
    decline_rows = [
        row for row in change_rows if float(row["delta"]) < 0 and float(row["previous_spend"]) > 0
    ]
    newly_spent_rows = [
        row for row in change_rows if float(row["previous_spend"]) <= 0 and float(row["delta"]) > 0
    ]
    growth_rows.extend(newly_spent_rows)
    stopped_rows = [
        {
            "material": previous,
            "previous_spend": previous.spend,
        }
        for material_id, previous in previous_by_id.items()
        if previous.spend > 0
        and (
            material_id not in current_by_id
            or current_by_id[material_id].spend <= 0
        )
    ]

    new_share = (new_material_spend / total_spend * 100) if total_spend else 0.0
    assessment = (
        f"本日读取到 {len(materials)} 条素材，总消耗 {_currency(total_spend)}；"
        f"新素材 {len(new_materials)} 条，消耗 {_currency(new_material_spend)}，"
        f"占今日素材消耗 {new_share:.1f}%；跑量素材 {len(running)} 条，"
        f"消耗 {_currency(running_spend)}。"
    )

    directions: list[str] = []
    if winners:
        best = winners[0]
        directions.append(
            f"优先复刻「{_short_name(best.name)}」：综合ROI {_ratio(best.roi)}，"
            f"消耗 {_currency(best.spend)}，围绕同钩子、同卖点制作 3–5 条变体。"
        )
    elif new_materials:
        best_new = max(new_materials, key=lambda item: item.spend)
        directions.append(
            f"新素材中消耗最高的是「{_short_name(best_new.name)}」："
            f"消耗 {_currency(best_new.spend)}，ROI {_ratio(best_new.roi)}，"
            "先判断这条新素材是否值得继续放量。"
        )
    else:
        directions.append("暂时没有达到目标ROI的素材，先用痛点、效果演示、真实反馈三类方向补足素材池。")

    if growth_rows:
        top_growth = growth_rows[0]["material"]
        directions.append(
            f"继续观察放量素材「{_short_name(top_growth.name)}」："
            f"今日消耗 {_currency(top_growth.spend)}，较上一日增加。"
        )
    if losers:
        directions.append(
            "对高消耗低效素材「"
            + "」「".join(_short_name(item.name, 24) for item in losers[:2])
            + "」先降低测试优先级，不直接复制其结构。"
        )
    if stopped_rows:
        directions.append(
            "有素材已经停止消耗，先核对是主动暂停、预算撞线还是素材失效，再决定是否重新测试。"
        )
    directions.extend(
        [
            "新素材一次只改一个主要变量，保持商品、定向和落地页一致，方便对比。",
            "每天至少保留一批新素材测试位，优先验证前 3 秒钩子、卖点和信任证明。",
        ]
    )

    summary = {
        "material_count": len(materials),
        "total_material_spend": total_spend,
        "new_material_count": len(new_materials),
        "new_material_spend": new_material_spend,
        "running_material_count": len(running),
        "running_material_spend": running_spend,
        "previous_material_count": len(previous_materials or []),
        "growth_count": len(growth_rows),
        "decline_count": len(decline_rows),
        "stopped_count": len(stopped_rows),
    }
    return (
        assessment,
        _new_material_section(new_materials, new_material_spend, total_spend),
        _material_change_section(
            change_rows,
            growth_rows,
            decline_rows,
            stopped_rows,
            previous_materials is not None,
        ),
        directions,
        summary,
    )


def build_material_analysis(
    plan: PlanSnapshot | None,
    event: MonitorEvent | None,
    generated_at: datetime | None = None,
    materials: list[MaterialMetric] | None = None,
    report_date: date | None = None,
    materials_error: str | None = None,
    previous_materials: list[MaterialMetric] | None = None,
) -> dict:
    now = generated_at or datetime.now(UTC)
    analysis_date = report_date or now.astimezone().date()
    metrics = event.metrics if event is not None else None
    roi_target = plan.roi_goal if plan is not None else None
    roi = metrics.roi if metrics is not None else plan.roi if plan is not None else None
    roi_met = None if roi_target is None else (roi is not None and roi >= roi_target)

    if materials is not None and (materials or previous_materials):
        assessment, new_section, change_section, directions, summary = _material_analysis(
            materials,
            previous_materials,
            roi_target,
            analysis_date,
        )
    else:
        assessment, directions = _generic_directions(roi_met)
        summary = {
            "material_count": 0,
            "total_material_spend": 0.0,
            "new_material_count": 0,
            "new_material_spend": 0.0,
            "running_material_count": 0,
            "running_material_spend": 0.0,
            "previous_material_count": len(previous_materials or []),
            "growth_count": 0,
            "decline_count": 0,
            "stopped_count": 0,
        }
        if materials_error:
            detail = f"素材明细读取失败：{materials_error}"
        else:
            detail = "当前页面暂未暴露稳定的素材级明细，本报告先基于直播间整体投放结果生成新素材方向。"
        new_section = detail
        change_section = "未读取到可对比的素材消耗数据。"

    metrics_payload = metrics.model_dump(mode="json") if metrics is not None else {}
    metrics_payload.update(summary)
    report = f"""## 素材分析报告｜{analysis_date.isoformat()}

### 一、每日素材消耗概况

- 计划：{plan.name if plan is not None else "暂无法读取"}
- 素材总消耗：{_currency(summary["total_material_spend"])}
- 有消耗素材数：{summary["material_count"]}
- 新素材上新：{summary["new_material_count"]} 条
- 新素材消耗：{_currency(summary["new_material_spend"])}
- 跑量素材数：{summary["running_material_count"]} 条
- 跑量素材消耗：{_currency(summary["running_material_spend"])}
- 综合成本：{_currency(metrics.spend if metrics is not None else None)}
- 综合营销 ROI：{_ratio(roi)}
- 净成交金额：{_currency(metrics.gmv if metrics is not None else None)}
- 整体成交订单数：{metrics.orders if metrics is not None else "--"}
- GPM：{_currency(metrics.gpm) if metrics is not None and metrics.gpm is not None else "--"}
- 目标ROI：{_ratio(roi_target)}
- 长期策略约束：{event.banner if event is not None else "暂无法读取"}

{assessment}

### 二、新素材情况

{new_section}

### 三、跑量素材较上一日变化

{change_section}

### 四、素材产出方向

{chr(10).join(f"- {item}" for item in directions)}

### 五、执行提醒

- 本报告只提供素材产出和调整方向，不自动上传、替换或绑定素材。
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
    previous_materials = None
    materials_error = None
    if material_reader is not None and analysis_date is not None:
        try:
            materials = await material_reader.read(analysis_date)
        except Exception as exc:  # noqa: BLE001
            materials_error = str(exc)
        if materials is not None:
            try:
                previous_materials = await material_reader.read(
                    analysis_date - timedelta(days=1)
                )
            except Exception:  # noqa: BLE001
                previous_materials = None
    report = store.add_if_absent(
        build_material_analysis(
            plan_provider(),
            event,
            materials=materials,
            previous_materials=previous_materials,
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
