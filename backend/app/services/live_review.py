import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.services.analytics import ComputedMetrics
from app.services.monitor import MonitorProfile
from app.services.self_check import render_self_check, self_check, verify_data
from app.services.thresholds import resolve_thresholds as _resolve_thresholds
from app.services.thresholds import value_of as _threshold_value
from app.services.thresholds import text_of as _threshold_text

# 报告里统一使用的「参考线」。
# 注意：这些不是官方阈值，是我们自己的判断线，正文里必须显式标注出来。
# 全报告只允许引用这一处，避免出现「第四节说有问题、第七节说没问题」的自相矛盾。
LINE_EXPOSURE_VIEW_RATE = 4.0     # 曝光观看率（%）
LINE_VIEW_CONVERSION_RATE = 5.0   # 观看成交转化率（%）
LINE_GPM = 3500.0                 # GPM（元）
LINE_CPM = 100.0                  # CPM（元）
LINE_TOTAL_VIEWS = 2000           # 整场观看人数
LINE_END_ONLINE = 15              # 结束在线人数
LINE_ASSIST_SHARE = 50.0          # 追投/调控消耗占比（%），官方建议约 25%
OFFICIAL_ASSIST_SHARE = 25.0      # 官方《素材追投调控产品手册》建议值

REVIEW_PATH = Path(__file__).resolve().parents[3] / ".local" / "live_reviews.json"
REVIEW_KNOWLEDGE_PATH = (
    Path(__file__).resolve().parents[3] / ".local" / "review_knowledge.json"
)


def _money(value: float | None) -> str:
    return "--" if value is None else f"¥{value:,.2f}"


def _ratio(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}"


def _clip(text: str, limit: int) -> str:
    """截断时带省略号，避免读到半句话。"""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip("；，,。") + "…"


def _pct(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}%"


def _cpm(metrics: ComputedMetrics) -> float | None:
    """千次曝光成本。"""
    exposure = metrics.exposure_count or 0
    if exposure <= 0 or metrics.spend <= 0:
        return None
    return metrics.spend / (exposure / 1000)


def _exposure_view_rate(snapshot: MetricSnapshot, metrics: ComputedMetrics) -> float | None:
    if snapshot.exposure_view_rate is not None:
        return snapshot.exposure_view_rate
    exposure = metrics.exposure_count or 0
    if exposure <= 0 or not metrics.view_count:
        return None
    return metrics.view_count / exposure * 100


def _flow_diagnosis(
    metrics: ComputedMetrics,
    cpm: float | None,
    ev_rate: float | None,
) -> tuple[list[str], list[str]]:
    """流量端：羽川体系里看 CPM、曝光、观看、进入率。"""
    problems: list[str] = []
    fixes: list[str] = []

    if cpm is not None and cpm > LINE_CPM:
        problems.append(
            f"流量成本偏高：CPM ¥{cpm:.1f}，说明拿量成本高（人群竞争激烈或素材/画面质量不够）"
            f"（依据：CPM ¥{cpm:.1f} > 参考线 ¥{LINE_CPM:,.0f}）"
        )
        fixes.append(
            f"降 CPM：本场 CPM ¥{cpm:.1f}。下场先不动出价，优先换 1～2 条新开场素材"
            "（前 3 秒直接上痛点和使用场景），把自然曝光拉起来"
        )
    if ev_rate is not None and ev_rate < LINE_EXPOSURE_VIEW_RATE:
        problems.append(
            f"曝光观看率偏低：{ev_rate:.2f}%，说明曝光进来了但没人点进直播间"
            "（素材封面/直播间画面吸引力不足）"
            f"（依据：{ev_rate:.2f}% < 参考线 {LINE_EXPOSURE_VIEW_RATE}%）"
        )
        fixes.append(
            f"提曝光观看率：本场 {ev_rate:.2f}%。下场换更直白的直播画面贴片"
            "（把「产品+效果+价格」写在画面上），并准备 2 条不同开场做 A/B"
        )
    if metrics.views and metrics.views < LINE_TOTAL_VIEWS:
        problems.append(
            f"进人不足：整场观看 {metrics.views} 人，流量池没打开"
            f"（依据：整场观看 {metrics.views} < 参考线 {LINE_TOTAL_VIEWS:,}）"
        )
        fixes.append("进场量：下场保持每天至少一批新素材测试位，同时用高潜素材做追投补量")
    return problems, fixes


def _reception_diagnosis(
    metrics: ComputedMetrics,
) -> tuple[list[str], list[str]]:
    """承接端：羽川体系里看 GPM、观看成交转化率、人均/在线。"""
    problems: list[str] = []
    fixes: list[str] = []

    if (
        metrics.view_conversion_rate is not None
        and metrics.view_conversion_rate < LINE_VIEW_CONVERSION_RATE
    ):
        problems.append(
            f"观看成交转化率偏低：{metrics.view_conversion_rate:.2f}%，"
            "流量进来了但没转化成订单（话术节奏/机制/价格没打透）"
            f"（依据：{metrics.view_conversion_rate:.2f}% < 参考线 "
            f"{LINE_VIEW_CONVERSION_RATE}%）"
        )
        fixes.append(
            f"提转化：本场观看成交转化率 {metrics.view_conversion_rate:.2f}%。"
            "下场按「产品→场景→意图」重排话术，把价格机制和试用装权益前置到前 20 分钟"
        )
    if metrics.gpm is not None and metrics.gpm < LINE_GPM:
        problems.append(
            f"GPM 偏低：¥{metrics.gpm:,.0f}，单位观看的产出不够，是 ROI 上不去的直接原因"
            f"（依据：GPM ¥{metrics.gpm:,.0f} < 参考线 ¥{LINE_GPM:,.0f}）"
        )
        fixes.append(
            f"提 GPM：本场 ¥{metrics.gpm:,.0f}。把讲解密度压到 8～10 分钟一轮，"
            "高转化品放在在线人数爬升的时段讲"
        )
    if metrics.online_viewers < LINE_END_ONLINE:
        problems.append(
            f"在线人数偏低：{metrics.online_viewers} 人，直播间没形成稳定在线"
            f"（依据：结束在线 {metrics.online_viewers} < 参考线 {LINE_END_ONLINE}）"
        )
        fixes.append("稳在线：先保证直播时长和单小时观看次数，不要频繁大幅调整出价")
    return problems, fixes


def _build_issues(
    metrics,
    cpm,
    ev_rate,
    threshold: float | None,
    lines: dict | None = None,
) -> list[dict]:
    """把数据问题整理成「现象 + 归因 + 依据」的结构。

    lines = resolve_thresholds() 的结果：每条判断线都带"来源"
    （你设定的 / 本账户分位 / 通用参考线），依据里必须如实写明是谁定的。
    """
    issues: list[dict] = []
    limits = lines or {}

    ev_limit = _threshold_value(limits, "exposure_view_rate", LINE_EXPOSURE_VIEW_RATE)
    conv_limit = _threshold_value(
        limits, "view_conversion_rate", LINE_VIEW_CONVERSION_RATE
    )
    gpm_limit = _threshold_value(limits, "gpm", LINE_GPM)
    cpm_limit = _threshold_value(limits, "cpm", LINE_CPM)

    def add(focus, phenomenon, basis):
        issues.append({
            "focus": focus,
            "phenomenon": phenomenon,
            "attribution": ATTRIBUTION.get(focus, []),
            "basis": basis,
        })

    if ev_rate is not None and ev_rate < ev_limit:
        add(
            "曝光观看率",
            f"曝光 {metrics.exposure_count or 0:,} 次，只有 {metrics.view_count or 0:,} 次观看，"
            f"曝光观看率 {ev_rate:.2f}%"
            f"（依据：{_threshold_text(limits, 'exposure_view_rate', LINE_EXPOSURE_VIEW_RATE, '%')}）。"
            "说明**曝光给到了但没人点进来**",
            "官方《优质直播间规则说明书》基础质量·画面",
        )
    if (
        metrics.view_conversion_rate is not None
        and metrics.view_conversion_rate < conv_limit
    ):
        add(
            "观看成交转化率",
            f"观看 {metrics.view_count or 0:,} 次，成交 {metrics.orders} 单，"
            f"观看成交转化率 {metrics.view_conversion_rate:.2f}%"
            f"（依据：{_threshold_text(limits, 'view_conversion_rate', LINE_VIEW_CONVERSION_RATE, '%')}）。"
            "说明**人进来了但没转化成订单**",
            "官方《优质直播间规则说明书》内容价值·交易价值",
        )
    if metrics.gpm is not None and metrics.gpm < gpm_limit:
        add(
            "GPM",
            f"GPM ¥{metrics.gpm:,.0f}"
            f"（依据：{_threshold_text(limits, 'gpm', LINE_GPM, ' 元')}），"
            "单位观看产出不够，是 ROI 上不去的直接原因",
            "官方《优质直播间规则说明书》内容讲解要求",
        )
    if cpm is not None and cpm > cpm_limit:
        add(
            "CPM",
            f"CPM ¥{cpm:.1f}"
            f"（依据：{_threshold_text(limits, 'cpm', LINE_CPM, ' 元')}），拿量成本偏高",
            "官方《CPM 高低由什么决定》",
        )

    if metrics.roi is not None and threshold is None:
        # 目标没配置就不能假装有目标去算缺口，否则会写出「目标 2.00」这种假数据
        issues.append({
            "focus": "ROI",
            "phenomenon": (
                f"整体 ROI {metrics.roi:.2f}，但账户未配置目标 ROI，**无法判断是否达标**"
            ),
            "attribution": [
                "① 投放策略里没填 ROI 目标 → 达标与否无参照，先补齐目标",
                "② 补齐后再按本场实际水平定目标，不要凭感觉设一个偏高的值",
            ],
            "basis": "投放策略（profile）未配置 roi_target",
        })
    elif metrics.roi is not None and metrics.roi < threshold:
        gap = threshold - metrics.roi
        causes = []
        if ev_rate is not None and ev_rate < ev_limit:
            causes.append(
                f"① 曝光观看率 {ev_rate:.2f}% 偏低"
                f"（{_threshold_text(limits, 'exposure_view_rate', LINE_EXPOSURE_VIEW_RATE, '%')}）"
                "→ 曝光没转化成进人，直接吃掉 ROI"
            )
        if (
            metrics.view_conversion_rate is not None
            and metrics.view_conversion_rate < conv_limit
        ):
            causes.append(
                f"② 观看成交转化率 {metrics.view_conversion_rate:.2f}% 偏低"
                f"（{_threshold_text(limits, 'view_conversion_rate', LINE_VIEW_CONVERSION_RATE, '%')}）"
                "→ 进人后没成交，GPM 上不去"
            )
        if cpm is not None and cpm > cpm_limit:
            causes.append(
                f"③ CPM ¥{cpm:.1f} 偏高"
                f"（{_threshold_text(limits, 'cpm', LINE_CPM, ' 元')}）"
                "→ 拿量成本吃掉利润空间"
            )
        if metrics.gpm is not None and metrics.gpm < gpm_limit:
            causes.append(
                f"④ GPM ¥{metrics.gpm:,.0f} 偏低"
                f"（{_threshold_text(limits, 'gpm', LINE_GPM, ' 元')}）"
                "→ 单位观看产出不够"
            )
        if not causes:
            causes.append("未定位到单一主因，需要结合上面各环节数据进一步排查")
        issues.append({
            "focus": "ROI",
            "phenomenon": f"整体 ROI {metrics.roi:.2f}，目标 {threshold:.2f}，"
                          f"缺口 {gap:.2f}（低 {gap / threshold * 100:.0f}%）",
            "attribution": causes,
            "basis": "千川计划 ROI 目标 + 本场三因子拆解",
        })
    return issues


def _render_issues(issues: list[dict]) -> str:
    if not issues:
        return "- 本场未发现明显异常，流量和承接都在正常区间"
    lines = []
    for idx, item in enumerate(issues, 1):
        lines.append(f"**问题 {idx}：{item['focus']}**")
        lines.append("")
        lines.append(f"- **现象**：{item['phenomenon']}")
        if item["attribution"]:
            lines.append("- **归因（按可能性排序）**：")
            lines += [f"  - {a}" for a in item["attribution"]]
        lines.append(f"- **依据**：{item['basis']}")
        lines.append("")
    return "\n".join(lines)


def _render_solutions(issues: list[dict]) -> str:
    lines = []
    n = 0
    for item in issues:
        sol = SOLUTIONS.get(item["focus"])
        if not sol:
            continue
        n += 1
        lines += _render_solution(f"方案 {n}｜{item['focus']}", sol)
    if not lines:
        return "- 本场无需要调整的动作"
    lines.append("> 所有动作都需你确认后执行；调整间隔 ≥1 小时、单次幅度 ≤±10%，否则失去成本保障。")
    return "\n".join(lines)


def build_site_change_section(changes: list[dict], logs: list[dict]) -> str:
    """人货场变更及影响：对比变更前后 60 分钟的核心指标。"""
    if not changes:
        return ""
    lines = ["### 本场人货场变更及影响", ""]
    lines.append("> 人货场一变，盯盘指标就不能直接和上一场对比；这里单独看变更前后的数据差异。")
    lines.append("")

    def parse_ts(v):
        try:
            return datetime.fromisoformat(str(v))
        except Exception:  # noqa: BLE001
            return None

    sample = []
    for item in logs:
        ts = parse_ts(item.get("created_at"))
        if ts is not None:
            sample.append((ts, item))
    sample.sort(key=lambda p: p[0])

    for ch in changes[:3]:
        ts = parse_ts(ch.get("changed_at"))
        label = f"{ts.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%m-%d %H:%M') if ts else '--'}"
        lines.append(f"**变更：{ch.get('type')}（{label}）**")
        if ch.get("note"):
            lines.append(f"- 说明：{ch['note']}")
        if ts is None or not sample:
            lines.append("- 暂无可对比的盯盘数据（变更时间需要确认）")
            lines.append("")
            continue
        before = [x for t, x in sample if ts.timestamp() - 3600 <= t.timestamp() < ts.timestamp()]
        after = [x for t, x in sample if ts.timestamp() <= t.timestamp() < ts.timestamp() + 3600]

        def avg(rows, key):
            vals = [float(r.get(key)) for r in rows if isinstance(r.get(key), (int, float))]
            return sum(vals) / len(vals) if vals else None

        def line_of(name, key, unit=""):
            b, a = avg(before, key), avg(after, key)
            if b is None or a is None:
                return f"- {name}：数据不足（变更前 {len(before)} 条 / 变更后 {len(after)} 条采样）"
            delta = a - b
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            return (f"- {name}：变更前 {b:,.2f}{unit} → 变更后 {a:,.2f}{unit}"
                    f"（{arrow} {abs(delta):,.2f}）")

        if before and after:
            lines.append(f"- 采样：变更前 {len(before)} 条 / 变更后 {len(after)} 条")
            lines.append(line_of("ROI", "roi"))
            lines.append(line_of("GPM", "gpm", " 元"))
            lines.append(line_of("CPM", "cpm", " 元"))
            lines.append(line_of("曝光观看率", "exposure_view_rate", "%"))
            lines.append(line_of("观看成交转化率", "view_conversion_rate", "%"))
            lines.append(line_of("在线人数", "online_viewers", " 人"))
            b_roi, a_roi = avg(before, "roi"), avg(after, "roi")
            if b_roi is not None and a_roi is not None:
                if a_roi > b_roi + 0.05:
                    lines.append("- **判断**：画面变更后 ROI 回升，说明新画面更有效，建议保持并观察能否稳定")
                elif a_roi < b_roi - 0.05:
                    lines.append("- **判断**：画面变更后 ROI 下滑，需要回看新画面是否影响了信息传达（对照官方优质直播间·画面标准），必要时回退或局部调整")
                else:
                    lines.append("- **判断**：画面变更前后 ROI 基本持平，说明这次变更对投放影响不大")
        else:
            lines.append(f"- 数据不足：变更前 {len(before)} 条 / 变更后 {len(after)} 条采样")
        lines.append("")
    return "\n".join(lines)


def _traffic_analysis(sources: dict) -> tuple[list[str], list[str], list[str]]:
    """返回 (判断, 建议, 表格行)。"""
    if not sources:
        return ["未读取到直播间流量结构（大屏未展示成交渠道构成）"], [], []
    ordered = sorted(sources.items(), key=lambda kv: kv[1], reverse=True)
    rows = [f"| {name} | {value:.2f}% |" for name, value in ordered]

    judgments: list[str] = []
    fixes: list[str] = []

    top_name, top_value = ordered[0]
    judgments.append(f"最大来源是「{top_name}」占 {top_value:.1f}%")

    if top_name == "短视频及图文引流" and top_value >= 35:
        judgments.append(
            f"素材依赖度高：短视频及图文引流占 {top_value:.1f}%，"
            "素材一旦衰退，进场量会直接掉"
        )
        fixes.append(
            "降低素材依赖：每天保留至少一批新素材测试位，不要只靠头部素材撑量"
        )

    natural = sources.get("直播推荐", 0) + sources.get("抖音商城推荐", 0)
    if natural < 20:
        judgments.append(
            f"自然推荐偏弱：直播推荐 + 抖音商城推荐合计仅 {natural:.1f}%，"
            "说明直播间自身吸引力（画面/话术/停留）还没带起自然流量"
        )
        fixes.append(
            "提自然推荐：优化直播画面贴片和开场话术，把停留时长和互动做起来"
        )

    if sources.get("搜索", 0) >= 15:
        judgments.append(
            f"搜索占比 {sources['搜索']:.1f}%，有稳定的主动搜索需求，"
            "这批人意图明确但没完全接到直播间"
        )
        fixes.append("接搜索流量：补齐商品标题/主图和商品卡，把搜索人群引导进直播间")

    if sources.get("其他", 0) >= 20:
        judgments.append(
            f"「其他」占 {sources['其他']:.1f}% 偏高，来源不明确，需要留意是否存在低质流量"
        )

    return judgments, fixes, rows


def build_spend_structure(split: dict | None) -> tuple[str, list[str], list[str]]:
    """素材口径的消耗结构（基础 / 追投调控），返回 (章节, 追加问题, 追加方案)。"""
    if not split:
        return "", [], []
    basic = float(split.get("basic_spend") or 0)
    assist = float(split.get("assist_spend") or 0)
    total = basic + assist
    if total <= 0:
        return "", [], []
    ratio = assist / total * 100

    section = "\n".join(
        [
            "### 消耗结构（素材口径）",
            "",
            "| 项目 | 金额 | 占比 |",
            "| --- | ---: | ---: |",
            f"| 基础计划消耗 | ¥{basic:,.2f} | {basic / total * 100:.1f}% |",
            f"| 追投/调控消耗 | ¥{assist:,.2f} | {ratio:.1f}% |",
            "",
            f"> 素材口径整体消耗 ¥{float(split.get('total_spend') or total):,.2f}",
        ]
    )

    problems: list[str] = []
    fixes: list[str] = []
    if ratio > LINE_ASSIST_SHARE:
        problems.append(
            f"追投占比过高：追投/调控 ¥{assist:,.2f} 占 {ratio:.1f}%，"
            f"高于基础计划 ¥{basic:,.2f}"
            f"（依据：追投占比 {ratio:.1f}% > 参考线 {LINE_ASSIST_SHARE:.0f}%，"
            "说明基础计划跑不动量；官方《素材追投调控产品手册》建议控成本追投"
            f"占账户总消耗约 {OFFICIAL_ASSIST_SHARE:.0f}%）"
        )
        fixes.append(
            f"降追投占比：下调追投整体预算 20%~30%，把量让给基础计划，"
            "10~20 分钟后看基础消耗能否回升（目标：基础占比 > 40%）"
        )
    else:
        fixes.append(
            f"消耗结构正常（基础 {basic / total * 100:.1f}% / 追投 {ratio:.1f}%），维持当前结构"
        )
    return section, problems, fixes


def insert_sections(markdown: str, sections: list[str]) -> str:
    """把附加章节插到「历史对照」之前。"""
    anchor = "### 八、历史对照与学习沉淀"
    body = "\n\n".join(s for s in sections if s)
    if not body:
        return markdown
    if anchor in markdown:
        return markdown.replace(anchor, body + "\n\n" + anchor, 1)
    return markdown + "\n\n" + body


def append_review_items(markdown: str, problems: list[str], fixes: list[str]) -> str:
    """把补充的问题/方案追加进对应章节。"""
    if problems:
        marker = "### 四、具体问题\n"
        if marker in markdown:
            head, rest = markdown.split(marker, 1)
            block, tail = rest.split("\n### ", 1)
            block = block.rstrip() + "\n" + "\n".join(f"- {p}" for p in problems) + "\n"
            markdown = head + marker + block + "\n### " + tail
    if fixes:
        marker = "### 五、具体解决方案\n"
        if marker in markdown:
            head, rest = markdown.split(marker, 1)
            block, tail = rest.split("\n### ", 1)
            existing = [line for line in block.splitlines() if line.strip()]
            start = len([line for line in existing if line[:2].rstrip(".").isdigit()])
            extra = [
                f"{start + i + 1}. {item}" for i, item in enumerate(fixes)
            ]
            block = block.rstrip() + "\n" + "\n".join(extra) + "\n"
            markdown = head + marker + block + "\n### " + tail
    return markdown


ATTRIBUTION = {
    "曝光观看率": [
        "① 直播间画面贴片信息不清晰/被遮挡（官方要求：出镜主体无遮挡、信息清晰完整展示）",
        "② 素材与人群不匹配（素材带「人货场」向量，向量不对就吸不到人）",
        "③ 画质/光线/滤镜问题（官方建议 1080p、光线明亮、无夸张美颜滤镜）",
        "④ 封面与开头 3 秒没有直接给到用户关心的点",
    ],
    "观看成交转化率": [
        "① 话术节奏没打透（卖点、价格机制、权益没在前 20 分钟讲清）",
        "② 直播间在线人数不足，缺少氛围和从众效应",
        "③ 商品组合/价格机制与人群预期不匹配",
        "④ 售后保障（试用装、退换）没讲明白，用户不敢下单",
    ],
    "GPM": [
        "① 讲品密度低，单位时间产出不够（官方：讲解要聚焦 1~3 个核心卖点）",
        "② 高转化品没放在在线人数爬升时段讲",
        "③ 流量精准度不够，进来的人没有购买意图",
    ],
    "CPM": [
        "① 人群竞争激烈，自然成交能力弱（官方：CPM 取决于自然成交能力）",
        "② 素材质量不够，系统给的流量成本高",
        "③ 直播间承接能力弱，拉高了整体拿量成本",
    ],
    "在线人数": [
        "① 曝光观看率低，进人不够",
        "② 停留时长不足，进来就走",
        "③ 直播时段或频次不足，单小时观看次数没起来",
    ],
    "追投占比": [
        "① 基础计划跑不动量，只能靠追投补（官方：追投量级太大反而抢主计划量）",
        "② 调控预算设得过高（官方建议占账户总消耗 25% 左右）",
        "③ 主计划 ROI 目标设得过高，拿不到量",
    ],
}


SOLUTIONS = {
    "曝光观看率": {
        "action": "重做直播画面贴片 + 换 2 条新开场素材",
        "steps": [
            "① 画面固定「产品名 + 核心功效 + 价格机制」三行字，字号不小于屏高的 8%，位置放左上角不挡主体",
            "② 撤掉遮挡出镜主体的贴纸/挂件（官方标准：出镜主体无遮挡、信息清晰完整展示）",
            "③ 拍 2 条不同开场的新素材各投 300~500 元测试：A 用痛点提问开场（「头油头屑反复？」），B 用效果对比开场",
            "④ 检查画质（建议 1080p）、光线和滤镜，关掉夸张美颜",
        ],
        "owner": "中控/设计（画面贴片）＋ 素材组（2 条视频）",
        "when": "下场开播前 2 小时完成；开播后第 1 小时看第一次数据",
        "verify": "曝光观看率从当前值提升到 4% 以上，并连续 2 小时稳定",
        "basis": "官方《优质直播间规则说明书》基础质量·画面 + 官方素材向量逻辑",
    },
    "观看成交转化率": {
        "action": "重排话术节奏 + 前置价格机制",
        "steps": [
            "① 每轮讲解压到 8~10 分钟：痛点 2 分钟 → 产品演示 3 分钟 → 价格机制 2 分钟 → 逼单 2 分钟",
            "② 把「赠品/试用装/售后保障」从原来放在最后，提到讲解前 20 分钟内说明",
            "③ 主播每轮讲完做一次互动提问（评论区扣 1），中控配合把在线氛围拉起来",
        ],
        "owner": "主播 + 中控（话术脚本由运营提前写好）",
        "when": "下场开播前完成脚本；开播后每 2 小时复盘一次转化率",
        "verify": "观看成交转化率提升 1 个百分点以上（如 4.66% → 5.7%）",
        "basis": "官方《优质直播间规则说明书》内容价值 + 交易价值",
    },
    "GPM": {
        "action": "压缩讲品密度 + 高转化品卡在人数爬升期",
        "steps": [
            "① 把爆款/高转化品放在在线人数爬升的时段讲解（不要平均分配）",
            "② 降低低效品的讲解时长，把时间让给高转化品",
            "③ 每轮讲解只聚焦 1~3 个核心卖点，不要罗列全部参数",
        ],
        "owner": "运营（排品 + 时段表）＋ 主播（执行）",
        "when": "下场开播前完成排品时段表",
        "verify": "GPM 提升 10% 以上",
        "basis": "官方《优质直播间规则说明书》内容讲解要求",
    },
    "追投占比": {
        "action": "把追投/调控占比从当前降到 40% 以下",
        "steps": [
            "① 列出当前所有调控任务，按「消耗 ÷ ROI」排序，先关掉 ROI 最低的 20~30%",
            "② 用「一键控量」下调，不要用卡预算或频繁起停（官方明确：会导致反复冷启）",
            "③ 单次调整幅度不超过 20%，调整间隔 ≥1 小时",
            "④ 观察基础计划消耗能否接上；接不上再考虑降主计划 ROI 目标",
        ],
        "owner": "投手",
        "when": "分 2~3 次调整，每次间隔 ≥1 小时",
        "verify": "追投占比降到 40% 以下，且基础计划消耗上升、整体 ROI 不继续下滑",
        "basis": "官方《素材追投调控产品手册》建议 25% + 成本保障规则",
    },
    "ROI": {
        "action": "先定位是「流量端」还是「承接端」拖的，再动出价/ROI 目标",
        "steps": [
            "① 先看三因子：CPM（拿量成本）、曝光观看率（素材/画面吸引力）、GPM（承接效率）哪个最差，先修最差的那一项",
            "② 承接端差（GPM 低）→ 先排品和话术，别急着动计划：把高转化品卡在在线人数爬升时段讲",
            "③ 流量端差（CPM 高）→ 换素材、扩人群池，先跑 2~3 条新素材各 300~500 元",
            "④ 基础 ROI 达标但整体不达标 → 先降追投/调控占比，把量让给基础计划，再看整体 ROI 能不能回来",
            "⑤ 要调 ROI 目标时：间隔 ≥1 小时、单次幅度 ≤±10%，否则失去成本保障",
        ],
        "owner": "投手（定方向）+ 运营（排品/话术）",
        "when": "本场复盘后定方向，下场开播前落地；盘中只在出现信号时调整",
        "verify": "下场整体 ROI 回到目标之上，或缺口较本场收窄 50% 以上",
        "basis": "官方《全域投放-推直播间产品手册》+ ROI = GPM ÷ CPM × 曝光观看率",
    },
    "CPM": {
        "action": "提高自然成交能力（换素材 + 扩人群池）",
        "steps": [
            "① 分析直播间高转化人群，找出核心产品兴趣词",
            "② 拍带「自然成交能力」的素材（前 3 秒直接展示产品使用场景）",
            "③ 每天保留至少 1 批新素材测试位，不要只靠头部素材",
        ],
        "owner": "素材组 + 投手",
        "when": "持续做，每 3 天评估一次 CPM 变化",
        "verify": "CPM 下降 15% 以上",
        "basis": "官方《CPM 高低由什么决定》+ 羽川素材方法论",
    },
}


def _attribution_and_solution(focus: str, metrics, cpm, extra: dict | None = None) -> tuple[list[str], list[str]]:
    """按焦点返回 (归因列表, 具体操作步骤)。"""
    return ATTRIBUTION.get(focus, []), []


def _render_solution(title: str, sol: dict) -> list[str]:
    lines = [f"**【{title}】**", f"- 动作：{sol['action']}", "- 具体怎么做："]
    lines += [f"  {s}" for s in sol["steps"]]
    lines += [
        f"- 谁来做：{sol['owner']}",
        f"- 什么时候做：{sol['when']}",
        f"- 怎么算成功：{sol['verify']}",
        f"- 依据：{sol['basis']}",
        "",
    ]
    return lines


QUALITY_CHECKLIST = {
    "基础质量 · 声音": [
        "音质清晰，无杂音/爆音",
        "主播语速平稳、咬字清晰、普通话为主",
        "主播与助播音量接近，无抢词/同时发声",
        "声画匹配，无错位",
    ],
    "基础质量 · 画面": [
        "画质清晰（官方建议 1080p），无光斑噪点",
        "画面稳定，无持续抖动",
        "画面整洁，无大面积贴纸/字幕/挂件遮挡",
        "光线明亮，出镜主体（人+商品）轮廓清晰",
        "无夸张美颜滤镜，不影响商品细节展示",
    ],
    "人货场匹配": [
        "出镜人妆容得体、造型匹配人设与售卖货品",
        "商品摆放整齐、展台干净、有层次感",
        "背景整洁有序，与主播风格和商品场景匹配",
    ],
    "内容价值": [
        "讲解形式多样（平播过款 / 源头直销 等）",
        "内容有用有趣，能获取知识、增加信任",
    ],
    "交易价值": [
        "商品组合清晰，卖点聚焦 1~3 个核心点",
        "促销福利（赠品/机制）表达明确",
        "售后保障说明到位（试用装、退换等）",
    ],
}


def _quality_focus(metrics, cpm: float | None, ev_rate: float | None) -> list[str]:
    """用数据指向优先自查的维度。"""
    focus: list[str] = []
    if ev_rate is not None and ev_rate < LINE_EXPOSURE_VIEW_RATE:
        focus.append(
            f"曝光观看率 {ev_rate:.2f}%（低于参考线 {LINE_EXPOSURE_VIEW_RATE}%）"
            "→ 优先查【基础质量 · 画面】："
            "清晰度、光线、有无大面积贴纸遮挡、滤镜是否过重"
        )
    if (
        metrics.view_conversion_rate is not None
        and metrics.view_conversion_rate < LINE_VIEW_CONVERSION_RATE
    ):
        focus.append(
            f"观看成交转化率 {metrics.view_conversion_rate:.2f}%"
            f"（低于参考线 {LINE_VIEW_CONVERSION_RATE}%）→ 优先查【内容价值】+"
            "【交易价值】：讲解节奏、卖点聚焦、促销机制是否讲透"
        )
    if metrics.gpm is not None and metrics.gpm < LINE_GPM:
        focus.append(
            f"GPM ¥{metrics.gpm:,.0f}（低于参考线 ¥{LINE_GPM:,.0f}）→ 优先查【人货场匹配】："
            "主播人设与货品是否匹配、商品陈列和背景是否到位"
        )
    if cpm is not None and cpm > LINE_CPM:
        focus.append(
            f"CPM ¥{cpm:,.1f}（高于参考线 ¥{LINE_CPM:,.0f}）→ 优先查【基础质量】："
            "画面和声音质量直接影响系统给量成本"
        )
    if not focus:
        focus.append("数据未指向明显短板，按下面清单逐条自查即可")
    return focus


def _quality_section(metrics, cpm: float | None, ev_rate: float | None) -> str:
    lines = ["### 七、优质直播间标准对照（官方）", ""]
    lines.append("**数据指向：优先自查这几项**（下面的数值仅为参考线，不是官方阈值）")
    lines.append("")
    for item in _quality_focus(metrics, cpm, ev_rate):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("**官方检查清单（来自《巨量千川优质直播间规则说明书》）**")
    lines.append("")
    for group, items in QUALITY_CHECKLIST.items():
        lines.append(f"**{group}**")
        for item in items:
            lines.append(f"- [ ] {item}")
        lines.append("")
    lines.append("> 官方：优质素材/直播间会获得**专属流量激励**，且在 ROI、GMV 上更有优势。")
    return "\n".join(lines)


def _record_case(signature: dict) -> None:
    """把本场复盘沉淀成案例，供下场复盘引用（体现不断学习）。"""
    import json

    path = REVIEW_KNOWLEDGE_PATH
    try:
        items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (OSError, json.JSONDecodeError):
        items = []
    if not isinstance(items, list):
        items = []
    items = [item for item in items if item.get("date") != signature.get("date")]
    items.append(signature)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(items[-200:], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        return


def _similar_cases(
    target: float | None,
    roi: float | None,
    exclude_date: str | None = None,
    limit: int = 2,
) -> list[dict]:
    """找历史相似场次（ROI 接近），用于对照。"""
    import json

    path = REVIEW_KNOWLEDGE_PATH
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(items, list) or roi is None:
        return []
    scored = []
    for item in items:
        if exclude_date and item.get("date") == exclude_date:
            continue
        past = item.get("roi")
        if past is None:
            continue
        scored.append((abs(float(past) - roi), item))
    scored.sort(key=lambda pair: pair[0])
    return [item for _, item in scored[:limit]]


def build_live_review(
    snapshot: MetricSnapshot,
    metrics: ComputedMetrics,
    profile: MonitorProfile,
    captured_at: datetime | None = None,
    avg_online: float | None = None,
    online_samples: int = 0,
    roi_target: float | None = None,
    baselines: dict | None = None,
) -> dict:
    ended_at = captured_at or snapshot.captured_at
    # 优先用计划里实际的 ROI 目标（调用方传入），没有才退回策略里的配置值
    configured_target = profile.hard_constraints.get("roi_target")
    if isinstance(roi_target, (int, float)):
        target = float(roi_target)
    elif isinstance(configured_target, (int, float)):
        target = float(configured_target)
    else:
        target = None
    roi_met = None if target is None or metrics.roi is None else metrics.roi >= target
    room = snapshot.room_name or "未标注直播间"

    cpm = _cpm(metrics)
    ev_rate = _exposure_view_rate(snapshot, metrics)

    problems: list[str] = []
    fixes: list[str] = []

    # 1) 结果层
    if target is None:
        problems.append("未配置目标 ROI，无法判断本场是否达标")
        fixes.append("先补齐投放策略里的 ROI 目标和预算约束")
    elif metrics.roi is not None and metrics.roi < target:
        gap = target - metrics.roi
        cause = ""
        if cpm is not None and cpm > LINE_CPM:
            cause = f"，缺口主要来自流量成本高（CPM ¥{cpm:.1f} > 参考线 ¥{LINE_CPM:,.0f}）"
        elif metrics.gpm is not None and metrics.gpm < LINE_GPM:
            cause = (
                f"，缺口主要来自承接效率低（GPM ¥{metrics.gpm:,.0f} < 参考线 "
                f"¥{LINE_GPM:,.0f}）"
            )
        elif ev_rate is not None and ev_rate < LINE_EXPOSURE_VIEW_RATE:
            cause = (
                f"，缺口主要来自曝光观看率不足（{ev_rate:.2f}% < 参考线 "
                f"{LINE_EXPOSURE_VIEW_RATE}%，素材/画面吸引力不够）"
            )
        problems.append(
            f"ROI 未达标：本场 {metrics.roi:.2f}，目标 {target:.2f}，"
            f"缺口 {gap:.2f}（低 {gap / target * 100:.0f}%）{cause}"
        )
    elif metrics.roi is not None:
        fixes.append(
            f"ROI 达标（{metrics.roi:.2f} ≥ {target:.2f}）：保住本场的高转化素材和时段，"
            "下场小幅放量 10%~20% 验证流量质量"
        )

    # 2) 流量端 / 承接端
    flow_problems, flow_fixes = _flow_diagnosis(metrics, cpm, ev_rate)
    recv_problems, recv_fixes = _reception_diagnosis(metrics)
    problems.extend(flow_problems)
    problems.extend(recv_problems)
    fixes.extend(flow_fixes)
    fixes.extend(recv_fixes)

    if metrics.orders == 0:
        problems.append("本场没有成交订单，流量或承接至少有一环断了")
        fixes.append("下场先小预算跑通一条能出单的素材+话术组合，再谈放量")

    if not problems:
        problems.append("本场未发现明显异常，流量和承接都在正常区间")

    # 沉淀案例 + 找相似场次
    signature = {
        "date": (snapshot.live_started_at or ended_at)
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .strftime("%Y-%m-%d"),
        "room": room,
        "roi": metrics.roi,
        "gpm": metrics.gpm,
        "cpm": cpm,
        "spend": metrics.spend,
        "problems": problems[:3],
        "fixes": fixes[:3],
    }
    current_date = (snapshot.live_started_at or ended_at).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    similar = _similar_cases(target, metrics.roi, exclude_date=current_date)

    # 下场开播前准备（基于本场问题）
    prep: list[str] = []
    if target is not None and metrics.roi is not None and metrics.roi < target:
        prep.append("出价 / ROI 目标：不要从低往高拉，先按本场实际水平定目标，再逐场微调")
        prep.append("素材组合：按「种收一体」优先补 2～3 条开场有痛点、中段有机制的新素材")
        prep.append("计划结构：先降低追投占比，把量让给基础计划，再观察基础消耗能否起来")
    else:
        prep.append("出价 / ROI 目标：维持本场目标，放量幅度控制在 10%~20%")
        prep.append("素材组合：复刻本场高 ROI 素材的钩子和卖点，做 3～5 条变体")
        prep.append("计划结构：主力计划保持，补 1 条追投测试新素材")

    review_time = snapshot.live_started_at or ended_at
    date_text = review_time.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    start_text = (
        snapshot.live_started_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")
        if snapshot.live_started_at
        else "--"
    )
    end_text = ended_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")
    result_text = (
        "未配置"
        if target is None
        else ("无法判断" if roi_met is None else ("达标" if roi_met else "未达标"))
    )

    similar_text = "暂无历史对照场次（本场已作为第一条案例沉淀）"
    if similar:
        lines = []
        for item in similar:
            lines.append(
                f"- {item.get('date')}（{item.get('room')}）ROI {item.get('roi')}、"
                f"GPM {item.get('gpm')}；当时问题："
                + _clip("；".join(item.get("problems") or []), 60)
            )
        similar_text = "\n".join(lines)

    traffic_judgments, traffic_fixes, traffic_rows = _traffic_analysis(
        snapshot.traffic_sources or {}
    )
    traffic_table = (
        "\n".join(["| 渠道 | 占比 |", "| --- | ---: |", *traffic_rows])
        if traffic_rows
        else "（未读取到渠道构成）"
    )

    passed, verify_issues = verify_data(metrics)
    if not passed:
        # 数据没过校验：只出概况 + 校验结果，不做分析
        check_lines = ["### 本场数据校验（未通过）", ""]
        for item in verify_issues:
            check_lines.append(f"- ❌ {item}")
        check_lines += [
            "",
            "> **数据未通过校验，本场不出问题归因和调整方案。**"
            "请先核对数据来源（大屏读数 / 素材接口 / 投放管理页），确认无误后再做复盘分析。",
            "",
        ]
        head = f"""## ⚠️ 直播复盘｜{date_text}｜{room}（数据未通过校验）

### 一、本场概况

- **直播间：{room}**
- 场次：{start_text} — {end_text}
- 综合成本：{_money(metrics.spend)}
- 综合营销 ROI：{_ratio(metrics.roi)}（目标 {_ratio(target)}）
- 净成交金额：{_money(metrics.gmv)}
- 成交订单数：{metrics.orders}
- GPM：{_money(metrics.gpm)}
- CPM（千次曝光成本）：{_money(cpm)}
- 曝光观看率：{_pct(ev_rate)}
- 直播间整体观看次数：{f"{metrics.view_count:,}" if metrics.view_count else "--"}

"""
        report_text = head + "\n".join(check_lines) + "\n" + render_self_check(verify_issues)
        return {
            "id": str(uuid.uuid4()),
            "date": date_text,
            "room": room,
            "created_at": datetime.now(UTC).isoformat(),
            "ended_at": ended_at.isoformat(),
            "plan_id": None,
            "report_markdown": report_text,
            "metrics": metrics.model_dump(mode="json"),
            "self_check": verify_issues,
            "verify_passed": False,
        }

    issues = _build_issues(
        metrics, cpm, ev_rate, target, _resolve_thresholds(profile, baselines)
    )
    quality_section = _quality_section(metrics, cpm, ev_rate)

    report = f"""## 直播复盘｜{date_text}｜{room}

### 一、本场概况

- **直播间：{room}**
- 场次：{start_text} — {end_text}
- 综合成本：{_money(metrics.spend)}
- 综合营销 ROI：{_ratio(metrics.roi)}（目标 {_ratio(target)}，**{result_text}**）
- 净成交金额：{_money(metrics.gmv)}
- 成交订单数：{metrics.orders}
- GPM：{_money(metrics.gpm)}
- CPM（千次曝光成本）：{_money(cpm)}
- 曝光观看率：{_pct(ev_rate)}
- 观看成交转化率：{_pct(metrics.view_conversion_rate)}
- 直播间整体观看人数：{snapshot.views}
- **平均在线人数：{f'{avg_online:.0f} 人' if avg_online is not None else '--'}**{f'（基于本场 {online_samples} 次盯盘采样）' if online_samples else ''}

**数据漏斗（可核对，用来验证数据没读错）**

| 环节 | 数值 |
| --- | ---: |
| 直播间整体曝光次数 | {f"{metrics.exposure_count:,}" if metrics.exposure_count else "--"} |
| 直播间观看次数 | {f"{metrics.view_count:,}" if metrics.view_count else "--"} |
| 商品点击次数 | {f"{metrics.product_clicks:,}" if metrics.product_clicks else "--"} |
| 成交订单数 | {metrics.orders:,} |

> 校验规则：曝光 ≥ 观看次数 ≥ 商品点击 ≥ 成交订单。任一层倒挂即说明数据解析出错。

### 二、数据拆解

- 投放策略：{profile.business_direction}
- 主目标：{profile.primary_objective}
- ROI 公式拆解：`ROI = GPM ÷ CPM × 曝光观看率`
  - GPM {_money(metrics.gpm)}（承接端效率）
  - CPM {_money(cpm)}（流量端成本）
  - 曝光观看率 {_pct(ev_rate)}（素材/画面吸引力）

### 三、直播间流量结构

{traffic_table}

{chr(10).join(f"- {item}" for item in traffic_judgments)}

### 四、具体问题（现象 → 归因）

{_render_issues(issues)}

### 五、具体解决方案（落到操作）

{_render_solutions(issues)}

### 六、下场开播前准备

{chr(10).join(f"- {item}" for item in prep)}

{quality_section}

### 八、历史对照与学习沉淀

{similar_text}

- 本场已沉淀进复盘案例库，下场复盘会自动引用本场的 ROI / GPM 作为对照基准。

> 以上均为只读分析。任何预算、出价、计划或素材调整都必须人工确认后再执行。"""

    # 输出前自检：把「四、具体问题」里真正渲染出去的内容也一起送检，
    # 否则自检通过、正文却可能是无依据的结论。
    rendered = [
        f"{item['focus']}：{item['phenomenon']}（依据：{item['basis']}）"
        for item in issues
    ]
    review_issues = self_check(metrics, problems + rendered)
    report = report + "\n" + render_self_check(review_issues)
    if review_issues:
        report = report.replace(
            f"## 直播复盘｜{date_text}｜{room}",
            f"## ⚠️ 直播复盘｜{date_text}｜{room}（自检未通过）",
            1,
        )

    _record_case(signature)

    return {
        "id": str(uuid.uuid4()),
        "date": date_text,
        "room": room,
        "created_at": datetime.now(UTC).isoformat(),
        "ended_at": ended_at.isoformat(),
        "plan_id": None,
        "report_markdown": report,
        "metrics": metrics.model_dump(mode="json"),
        "signature": signature,
        "self_check": review_issues,
        "verify_passed": True,
    }


class LiveReviewStore:
    def __init__(self, path: Path = REVIEW_PATH) -> None:
        self.path = path

    def list_reviews(self) -> list[dict]:
        return self._read()

    def latest(self) -> dict | None:
        items = self._read()
        return items[0] if items else None

    def upsert(self, review: dict) -> dict:
        items = self._read()
        items = [item for item in items if item.get("date") != review.get("date")]
        items.append(review)
        self._write(items)
        return review

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
