import inspect
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.services.action_planner import PlanSnapshot
from app.services.monitor import MonitorEvent

MATERIAL_ANALYSIS_PATH = (
    Path(__file__).resolve().parents[3] / ".local" / "material_analyses.json"
)


def build_material_analysis(
    plan: PlanSnapshot | None,
    event: MonitorEvent | None,
    generated_at: datetime | None = None,
) -> dict:
    now = generated_at or datetime.now(UTC)
    metrics = event.metrics if event is not None else None
    roi_target = plan.roi_goal if plan is not None else None
    roi = metrics.roi if metrics is not None else plan.roi if plan is not None else None
    roi_met = None if roi_target is None else (roi is not None and roi >= roi_target)

    if roi_met is None:
        directions = [
            "保持商品和落地页不变，按痛点、效果、信任感各制作 2 条素材做并行测试。",
            "前 3 秒直接展示用户问题和产品使用场景，减少泛品牌介绍。",
            "增加真人实测、直播现场演示和用户评价，提升停留与转化。",
            "统一素材变量，只改变开场和表达方式，方便后续判断哪类内容更有效。",
        ]
        assessment = "尚未读取到 ROI 目标，先按通用优化方向生成素材建议。"
    elif roi_met:
        directions = [
            "复刻当前高 ROI 素材的前 3 秒钩子，保持同一产品卖点和表达节奏。",
            "围绕高转化素材制作 3–5 条变体，只替换开场画面、口播顺序或字幕样式。",
            "增加真实使用场景和直播切片，优先保留能直接说明产品效果的内容。",
            "保持新素材与原素材的商品、定向和落地页一致，避免同时更换多个变量。",
        ]
        assessment = "整体 ROI 达到目标，优先复制有效素材结构并做小幅变体。"
    else:
        directions = [
            "减少纯价格促销和泛流量表达，改为痛点、效果演示、真实反馈三类方向。",
            "前 3 秒直接展示用户问题和使用前后对比，避免长铺垫和重复品牌介绍。",
            "增加真人实测、直播现场演示和用户评价截图，强化停留与转化。",
            "按痛点、效果、信任感各制作 2 条素材，统一商品和落地页，方便后续对比。",
        ]
        assessment = "整体 ROI 未达到目标，新素材应减少泛化卖点，强化直接转化理由。"

    report = f"""## 素材分析报告｜{now.astimezone().strftime("%Y-%m-%d")}

### 一、投放概况

- 计划：{plan.name if plan is not None else "暂无法读取"}
- 综合成本：{"--" if metrics is None else f"¥{metrics.spend:,.2f}"}
- 综合营销 ROI：{"--" if roi is None else f"{roi:.2f}"}
- 净成交金额：{"--" if metrics is None else f"¥{metrics.gmv:,.2f}"}
- 整体成交订单数：{metrics.orders if metrics is not None else "--"}
- GPM：{"--" if metrics is None or metrics.gpm is None else f"¥{metrics.gpm:,.2f}"}

### 二、素材表现判断

- 目标ROI：{"--" if roi_target is None else f"{roi_target:.2f}"}

{assessment}

当前页面暂未暴露稳定的素材级明细，本报告先基于直播间整体投放结果生成新素材方向；后续接入素材级数据后会自动细化到单条素材。

### 三、新素材制作方向

{chr(10).join(f"- {item}" for item in directions)}

### 四、执行提醒

- 本报告只提供制作方向，不自动上传、替换或绑定素材。
- 素材调整属于账户写操作，必须先预览并由用户确认。
- 当前系统保持只读模式。"""
    return {
        "id": str(uuid.uuid4()),
        "date": now.astimezone().strftime("%Y-%m-%d"),
        "created_at": now.isoformat(),
        "report_markdown": report,
        "metrics": metrics.model_dump(mode="json") if metrics is not None else {},
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
        existing = next((item for item in items if item.get("date") == report.get("date")), None)
        if existing is not None:
            return existing
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
) -> dict:
    event = monitor_service.latest_event() if hasattr(monitor_service, "latest_event") else None
    if event is None:
        event = monitor_service.tick()
        if inspect.isawaitable(event):
            event = await event
    report = store.add_if_absent(build_material_analysis(plan_provider(), event))
    await hub.publish(
        {
            "type": "material_analysis",
            "id": report["id"],
            "message": report["report_markdown"],
            "created_at": report["created_at"],
        }
    )
    return report
