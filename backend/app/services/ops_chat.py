# -*- coding: utf-8 -*-
"""直播运营助手：一个能对话的资深直播运营。

和主聊天框的分工（跟用户约好的）：
  - 主聊天框：只讲「本场」，每场直播开始会清空
  - 这里：跨场次保留、按天归档，负责「每天汇报 + 复盘沉淀 + 交流」

三条硬规矩：
  1. 数据没通过校验就不下结论，宁可不判断；
  2. 没异常就明说「无异常」，不硬凑问题；
  3. 只读。任何预算 / 出价 / 计划 / 素材的写操作都必须走确认流程。
"""

import json
import re
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

OPS_CHAT_PATH = Path(__file__).resolve().parents[3] / ".local" / "ops_chat.json"
KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "docs" / "knowledge"
BEIJING = ZoneInfo("Asia/Shanghai")

PERSONA = (
    "你是「直播运营助手」，一位资深直播运营专家，负责这个千川账号的全部运营工作："
    "盯盘、复盘、素材分析、和用户沟通。\n"
    "回答要求：\n"
    "1) 只依据给你的上下文和官方资料说话，不要编造数字、阈值或历史；"
    "上下文里没有的数据就说「没读到」，不要脑补。\n"
    "2) 给结论必须带依据（哪份数据、哪个口径、哪个官方规则）。\n"
    "3) 给方案必须落到「谁做 / 什么时候做 / 怎么算成功」。\n"
    "4) 没有异常就直说没有异常，不要为了显得有产出而硬找问题。\n"
    "5) 你当前是只读的：任何预算、出价、计划、素材的改动都只能给建议，"
    "并提醒用户需要人工确认后执行。\n"
    "6) 说人话、结构清楚，别堆术语。"
)


def _money(value) -> str:
    try:
        return f"¥{float(value):,.2f}"
    except (TypeError, ValueError):
        return "--"


def _ratio(value) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "--"


class OpsChatStore:
    """运营助手对话记录。只追加，按天归档；不丢历史。"""

    def __init__(self, path: Path = OPS_CHAT_PATH) -> None:
        self.path = path
        # 读-改-写之间必须互斥：否则「盯盘告警」和「启动补跑复盘」同时写，
        # 后写的会把先写的那条盖掉（真实踩过：告警就这么丢了）。
        self._lock = threading.Lock()

    def list_messages(self, limit: int = 100) -> list[dict]:
        """按时间正序返回（老的在前），方便前端直接渲染。"""
        return self._read()[-limit:]

    def latest(self) -> dict | None:
        items = self._read()
        return items[-1] if items else None

    def append(
        self,
        role: str,
        content: str,
        kind: str = "chat",
        meta: dict | None = None,
    ) -> dict:
        with self._lock:
            return self._append_locked(role, content, kind, meta)

    def _append_locked(
        self,
        role: str,
        content: str,
        kind: str = "chat",
        meta: dict | None = None,
    ) -> dict:
        items = self._read()
        now = datetime.now(BEIJING)
        message = {
            "id": str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "day": now.date().isoformat(),
            "role": role,          # assistant | user
            "kind": kind,          # briefing | review | material | chat
            "content": content,
            "meta": meta or {},
        }
        items.append(message)
        self._write(items[-800:])
        return message

    def replace_daily_briefing(
        self,
        content: str,
        day: str | None = None,
        meta: dict | None = None,
    ) -> dict:
        """同一天只保留最新一份《每日运营汇报》。

        定时任务重跑、手动补跑、开机补跑都不该在对话里堆出好几份一样的日报。
        """
        target = day or datetime.now(BEIJING).date().isoformat()
        with self._lock:
            # 去重按「这份汇报覆盖哪一天」来看（meta.day），
            # 不能用消息自身的 day —— 那个是"生成于哪天"，跨天补跑时两者不一样，
            # 会导致同一份日报堆两条。
            items = [
                item
                for item in self._read()
                if not (
                    item.get("kind") == "briefing"
                    and (
                        (item.get("meta") or {}).get("day") or item.get("day")
                    )
                    == target
                )
            ]
            self._write(items)
            return self._append_locked(
                "assistant", content, kind="briefing", meta=meta or {"day": target}
            )

    def has_today(self, kind: str, day: str | None = None) -> bool:
        """今天是否已经发过这类消息（供定时任务防重复）。"""
        target = day or datetime.now(BEIJING).date().isoformat()
        return any(
            item.get("kind") == kind and item.get("day") == target
            for item in self._read()
        )

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
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _knowledge_excerpt(limit: int = 3500) -> str:
    """官方运营手册摘要（给模型当参考资料，不是让它整篇背）。"""
    for name in ("ops_playbook.md", "official_rules.md"):
        path = KNOWLEDGE_DIR / name
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text[:limit]
    return ""


def _watch_digest(report: dict | None) -> dict | None:
    """先把盯盘报表压成小字段，别把整篇 markdown 塞给模型。"""
    if not report:
        return None
    return {
        "时间": report.get("created_at"),
        "直播间": report.get("room_name"),
        "场次开始": report.get("live_started_at"),
        "数据源": report.get("source"),
        "ROI": report.get("roi"),
        "目标ROI": report.get("roi_target"),
        "消耗": report.get("spend"),
        "净成交": report.get("gmv"),
        "GPM": report.get("gpm"),
        "在线": report.get("online_viewers"),
        "订单": report.get("orders"),
        "发现的问题": (report.get("problems") or [])[:6],
        "给出的方案": (report.get("adjustments") or [])[:6],
        "校验是否通过": report.get("verify_passed"),
    }


def _review_digest(review: dict) -> dict:
    return {
        "日期": review.get("date"),
        "直播间": review.get("room"),
        "结束时间": review.get("ended_at"),
        "报告": str(review.get("report_markdown") or "")[:2500],
    }


def _analysis_digest(analysis: dict) -> dict:
    return {
        "日期": analysis.get("date"),
        "报告": str(analysis.get("report_markdown") or "")[:2000],
    }


def build_ops_context(
    *,
    profile=None,
    latest_watch: dict | None = None,
    reviews: list[dict] | None = None,
    analyses: list[dict] | None = None,
    history: list[dict] | None = None,
) -> dict:
    """给运营助手准备的只读上下文。"""
    strategy = None
    if profile is not None:
        strategy = {
            "业务方向": getattr(profile, "business_direction", None),
            "主目标": getattr(profile, "primary_objective", None),
            "约束": getattr(profile, "hard_constraints", None),
            "版本": getattr(profile, "version", None),
        }
    return {
        "角色": "直播运营助手（资深直播运营专家）",
        "权限": "只读：任何写操作都要用户人工确认后执行",
        "投放策略": strategy,
        "最新盯盘": _watch_digest(latest_watch),
        "最近复盘": [_review_digest(item) for item in (reviews or [])],
        "最近素材分析": [_analysis_digest(item) for item in (analyses or [])],
        "最近对话": [
            {"role": item.get("role"), "content": str(item.get("content") or "")[:600]}
            for item in (history or [])[-6:]
        ],
        "官方运营手册摘要": _knowledge_excerpt(),
    }


def _yesterday(day: date) -> date:
    return day - timedelta(days=1)


def _problem_key(text: str) -> str:
    """把「ROI 未达标：当前 1.72，目标 2.60…」归成「ROI 未达标」。

    同一类问题在一次盯盘里会反复出现（每 5 分钟一条），
    汇报里必须按「类」汇总，不能把 140 次采样堆成 269 条清单。
    """
    head = str(text or "").split("：", 1)[0].strip()
    head = head.replace("**", "").rstrip("：")
    # 去掉里面的具体数字，让同类归到一起
    head = re.sub(r"[0-9]+(?:\.[0-9]+)?", "#", head).strip()
    # 有些问题没有「：」分隔，整句都进来了 —— 截到第一个分隔符，别让标题变成一整句
    if len(head) > 24:
        cuts = [
            index
            for index in (head.find(sep) for sep in ("（", "(", "，", ",", "——", "—"))
            if index > 0
        ]
        if cuts:
            head = head[: min(cuts)].strip()
    if len(head) > 24:
        head = head[:24].rstrip() + "…"
    return head or "其它问题"


def _problem_summary(
    watch_reports: list[dict],
    review: dict | None,
    *,
    limit: int = 8,
) -> tuple[list[str], int]:
    """按类汇总待处理问题，返回（汇总行, 原始条数）。"""
    buckets: dict[str, list[str]] = {}
    total = 0
    for report in watch_reports:
        if report.get("verify_passed") is False:
            continue  # 没校验通过的数据不拿来当问题
        for item in report.get("problems") or []:
            buckets.setdefault(_problem_key(item), []).append(str(item))
            total += 1

    review_issues: list[str] = []
    if review:
        markdown = str(review.get("report_markdown") or "")
        section = markdown.split("### 四、具体问题", 1)
        if len(section) == 2:
            body = section[1].split("### 五、", 1)[0]
            for line in body.splitlines():
                stripped = line.strip()
                if stripped.startswith("**问题 "):
                    review_issues.append(stripped.strip("*").strip())

    lines: list[str] = []
    for key, items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        lines.append(
            f"{key}　—　出现 {len(items)} 次；最近一次：{_clip(items[-1], 90)}"
        )
    for issue in review_issues:
        lines.append(f"复盘归档问题：{issue}")
    if len(lines) > limit:
        lines = lines[:limit] + [f"（另有 {len(lines) - limit} 类问题，详见对应复盘）"]
    return lines, total


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip("；，,。") + "…"


def build_daily_briefing(
    *,
    day: date,
    watch_reports: list[dict] | None = None,
    reviews: list[dict] | None = None,
    analyses: list[dict] | None = None,
    profile=None,
) -> str:
    """拼《每日运营汇报》。

    今天的汇报讲「昨天」：复盘要点 + 素材情况 + 待处理问题 + 今日建议。
    没数据就如实写没数据，没异常就如实写没异常——不硬凑。
    """
    watch_reports = watch_reports or []
    reviews = reviews or []
    analyses = analyses or []
    target = _yesterday(day)
    target_text = target.isoformat()

    review = next((r for r in reviews if r.get("date") == target_text), None)
    analysis = next((a for a in analyses if a.get("date") == target_text), None)
    day_reports = [
        r for r in watch_reports if str(r.get("created_at") or "").startswith(target_text)
    ]
    problems, problem_hits = _problem_summary(day_reports, review)

    lines: list[str] = []
    lines.append(f"## 每日运营汇报｜{target_text}")
    lines.append("")
    room = next(
        (str(r.get("room_name")) for r in day_reports if r.get("room_name")), None
    ) or (str(review.get("room")) if review and review.get("room") else None)
    header_bits = [f"覆盖日期 {target_text}"]
    if room:
        header_bits.append(f"直播间 {room}")
    header_bits.append(f"盯盘采样 {len(day_reports)} 次")
    lines.append("> " + "　|　".join(header_bits))
    lines.append("")

    if problems:
        lines.append(
            f"**一句话结论**：昨日有 {len(problems)} 类待处理问题"
            f"（盯盘累计报出 {problem_hits} 次，已按类合并），见下方清单。"
        )
    elif day_reports or review:
        lines.append("**一句话结论**：昨日未发现需要处理的问题，按既有策略继续跑。")
    else:
        lines.append("**一句话结论**：昨日没有盯盘记录，也没有归档的复盘，这次汇报没有可判断的数据。")
    lines.append("")

    lines.append("### 一、昨日复盘要点")
    lines.append("")
    if review:
        markdown = str(review.get("report_markdown") or "")
        keep = markdown.split("### 七、")[0].strip()
        if len(keep) > 2500:
            keep = keep[:2500].rstrip() + "…"
        lines.append(keep)
        lines.append("- （完整复盘见「直播复盘」窗口）")
    else:
        lines.append(f"- 没有 {target_text} 的归档复盘（可能昨日没开播，或复盘尚未生成）。")
    lines.append("")

    lines.append("### 二、素材情况")
    lines.append("")
    if analysis:
        markdown = str(analysis.get("report_markdown") or "")
        lines.append(markdown.strip()[:2200])
    else:
        lines.append(f"- 没有 {target_text} 的素材分析。")
    lines.append("")

    lines.append("### 三、待处理问题清单")
    lines.append("")
    if problems:
        for index, item in enumerate(problems, 1):
            lines.append(f"{index}. {item}")
    else:
        lines.append("- 无。昨日盯盘没有报出需要处理的问题。")
    lines.append("")

    lines.append("### 四、今日建议")
    lines.append("")
    if profile is not None:
        objective = getattr(profile, "primary_objective", "") or "维持当前投放结构"
        constraints = getattr(profile, "hard_constraints", {}) or {}
        lines.append(f"- 主目标：{objective}")
        if constraints:
            lines.append(f"- 约束：{constraints}")
    if not problems:
        lines.append("- 保持现有计划结构和素材节奏，不做无谓调整（有信号再动手）。")
    else:
        lines.append(
            "- 今日第一优先级：把上面清单里 ROI / 消耗 / 素材相关的问题逐条落地，"
            "每条都要明确「谁做、什么时候做、怎么算成功」。"
        )
    lines.append("- 所有改动都需要你确认后再执行，系统当前只读。")
    lines.append("")

    lines.append(
        "> 口径说明：本汇报只汇总工具里已校验通过的盯盘、复盘、素材数据；"
        "缺失的部分会如实标注「没有」，不会补猜。"
    )
    return "\n".join(lines)


def collect_ops_context(state, *, profile=None, history_limit: int = 6) -> dict:
    """从 app.state 里捞齐运营助手需要的只读上下文。"""
    watch_service = getattr(state, "live_watch_service", None)
    latest_watch = (
        watch_service.store.latest() if watch_service is not None else None
    )
    review_store = getattr(state, "live_review_store", None)
    analysis_store = getattr(state, "material_analysis_store", None)
    chat_store = getattr(state, "ops_chat_store", None)
    return build_ops_context(
        profile=profile,
        latest_watch=latest_watch,
        reviews=(review_store.list_reviews()[-2:] if review_store is not None else []),
        analyses=(
            analysis_store.list_analyses()[-2:] if analysis_store is not None else []
        ),
        history=(chat_store.list_messages(limit=history_limit) if chat_store else []),
    )


def collect_briefing_inputs(state) -> dict:
    """每日汇报要用到的原始数据（盯盘 / 复盘 / 素材）。"""
    watch_service = getattr(state, "live_watch_service", None)
    review_store = getattr(state, "live_review_store", None)
    analysis_store = getattr(state, "material_analysis_store", None)
    return {
        "watch_reports": (
            watch_service.store.list_logs(limit=400) if watch_service else []
        ),
        "reviews": (review_store.list_reviews() if review_store else []),
        "analyses": (analysis_store.list_analyses() if analysis_store else []),
    }
