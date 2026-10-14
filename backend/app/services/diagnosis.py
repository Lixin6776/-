# -*- coding: utf-8 -*-
"""诊断引擎：从"指标罗列"升级为"逐层归因 + 交叉验证"。

设计原则：
1. 只出「有依据、能解释、可反驳」的结论
2. 每条结论说明：现象 → 推理链 → 环节归因 → 排除了什么
3. 用多指标交叉验证，避免单指标误判
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Diagnosis:
    """一条诊断结论。"""
    key: str                     # 环节标识：进人/承接/成本/调控/消耗
    conclusion: str              # 一句话结论
    evidence: list[str] = field(default_factory=list)   # 数据依据
    reasoning: str = ""          # 推理链（为什么这么判断）
    ruled_out: list[str] = field(default_factory=list)  # 排除了哪些可能
    confidence: str = "中"        # 置信度：高/中/低

    def render(self) -> str:
        lines = [f"**【{self.key}】{self.conclusion}**", ""]
        if self.evidence:
            lines.append("- 数据依据：")
            lines += [f"  - {e}" for e in self.evidence]
        if self.reasoning:
            lines.append(f"- 推理：{self.reasoning}")
        if self.ruled_out:
            lines.append("- 已排除：")
            lines += [f"  - {r}" for r in self.ruled_out]
        lines.append(f"- 置信度：{self.confidence}")
        return "\n".join(lines)


def _dev(current, base) -> float | None:
    """相对基线的偏离百分比。"""
    if current is None or base in (None, 0):
        return None
    return (float(current) - float(base)) / float(base) * 100


def diagnose(
    metrics,
    roi_target: float | None,
    baselines: dict | None = None,
    spend_split: dict | None = None,
    plan_splits: list[dict] | None = None,
    room_name: str | None = None,
    spend_delta: float | None = None,
) -> list[Diagnosis]:
    """输出诊断结论列表。"""
    base = baselines or {}
    target = roi_target if roi_target is not None else None
    target_text = f"{target:.2f}" if target is not None else "未加载（账户目标 ROI 还没读到）"
    _roi_now = getattr(metrics, "roi", None)
    roi_text = f"{_roi_now:.2f}" if _roi_now is not None else "未读到"
    out: list[Diagnosis] = []

    def b(key):
        info = base.get(key) or {}
        return info.get("median"), info.get("samples")

    # ---------- 信号：相对基线是否异常 ----------
    ev = getattr(metrics, "exposure_view_rate", None)
    ev_base, ev_n = b("exposure_view_rate")
    ev_dev = _dev(ev, ev_base)
    ev_low = ev_dev is not None and ev_dev <= -15

    gpm = metrics.gpm
    gpm_base, gpm_n = b("gpm")
    gpm_dev = _dev(gpm, gpm_base)
    gpm_low = gpm_dev is not None and gpm_dev <= -15

    cpm_now = None
    try:
        from app.services.live_watch import _cpm
        cpm_now = _cpm(metrics)
    except Exception:  # noqa: BLE001
        pass
    cpm_base, cpm_n = b("cpm")
    cpm_dev = _dev(cpm_now, cpm_base)
    cpm_high = cpm_dev is not None and cpm_dev >= 20

    conv = getattr(metrics, "view_conversion_rate", None)
    conv_base, conv_n = b("view_conversion_rate")
    conv_dev = _dev(conv, conv_base)
    conv_low = conv_dev is not None and conv_dev <= -20

    online = metrics.online_viewers
    on_base, on_n = b("online_viewers")
    on_dev = _dev(online, on_base)
    online_low = on_dev is not None and on_dev <= -30

    roi = metrics.roi
    roi_low = target is not None and roi is not None and roi < target

    def fmt_base(value, samples, unit=""):
        return f"自身基线 {value:,.2f}{unit}（{samples} 次采样）" if value is not None else "基线样本不足"

    # ---------- 交叉验证规则 ----------

    # 规则1：进人环节 —— 曝光观看率 + 在线同步走低
    if ev_low and (online_low or on_dev is None):
        ev_base_text = fmt_base(ev_base, ev_n, "%")
        out.append(Diagnosis(
            key="进人环节",
            conclusion="问题在「进人」——曝光给到了，但没人点进来",
            evidence=[
                f"曝光观看率 {ev:.2f}%（{ev_dev:+.0f}% vs {ev_base_text}）",
                f"在线人数 {online}（{on_dev:+.0f}% vs 基线）" if on_dev is not None else f"在线人数 {online}",
                (f"整体 ROI {roi_text}（目标 {target_text}）"
                 + ("——ROI 已达标但进人环节在恶化，需提前干预" if target and roi and roi >= target else "")),
            ],
            reasoning="曝光观看率与在线人数同步走低，说明流量到了但没转化成进人；"
                      "如果是承接问题，通常曝光观看率正常、只有转化率下滑。",
            ruled_out=[
                "承接环节：在线人数低不代表不会成交，需要转化率佐证——见下方信号",
            ],
            confidence="高" if (ev_low and online_low) else "中",
        ))

    # 规则2：承接环节 —— 进人正常但转化/GPM 走低
    elif (not ev_low) and (conv_low or gpm_low):
        out.append(Diagnosis(
            key="承接环节",
            conclusion="问题在「承接」——人进来了，但没转化成订单",
            evidence=[
                f"曝光观看率 {ev:.2f}%（{ev_dev:+.0f}%）→ 进人环节正常" if ev_dev is not None else "曝光观看率无基线",
                f"观看成交转化率 {conv:.2f}%（{conv_dev:+.0f}% vs {fmt_base(conv_base, conv_n, '%')}）" if conv_dev is not None else "",
                f"GPM ¥{gpm:,.0f}（{gpm_dev:+.0f}% vs {fmt_base(gpm_base, gpm_n, ' 元')}）" if gpm_dev is not None else "",
                (f"整体 ROI {roi_text}（目标 {target_text}）"
                 + ("——ROI 暂时达标，但承接在下滑" if target and roi and roi >= target else "")),
            ],
            reasoning="进人环节正常（曝光观看率没掉），但转化率和 GPM 同步下滑——"
                      "说明人群进来了但没买，问题在直播间的承接能力（话术/货品/机制）。",
            ruled_out=[
                "进人环节：曝光观看率正常，排除素材/画面吸引力问题",
            ],
            confidence="高" if (conv_low and gpm_low) else "中",
        ))

    # 规则3：成本环节 —— CPM 明显高于基线
    if cpm_high:
        out.append(Diagnosis(
            key="成本环节",
            conclusion="问题在「拿量成本」——CPM 高于自身常态，吃掉利润空间",
            evidence=[
                f"CPM ¥{cpm_now:.1f}（{cpm_dev:+.0f}% vs {fmt_base(cpm_base, cpm_n, ' 元')}）",
                f"整体 ROI {roi_text} 未达目标 {target_text}" if roi else "",
            ],
            reasoning="ROI = GPM ÷ CPM × 曝光观看率。CPM 抬升会直接压低 ROI，"
                      "而 CPM 取决于自然成交能力（官方口径）——人群竞争或素材质量变差。",
            ruled_out=[],
            confidence="中",
        ))

    # 规则4：调控拖累 —— 基础 ROI 达标但整体不达标
    # 优先用「同场次」的素材口径拆分（和直播大屏同一时间窗），避免整天数据串味。
    session_split = (spend_split or {}).get("split") or {}
    session_fired = False
    s_base_roi = session_split.get("basic_roi")
    s_assist_roi = session_split.get("assist_roi")
    s_total_roi = session_split.get("total_roi")
    if (
        target
        and s_base_roi is not None
        and s_total_roi is not None
        and s_base_roi >= target
        and s_total_roi < target
    ):
        assist_roi_text = f"{s_assist_roi:.2f}" if s_assist_roi is not None else "未读到"
        out.append(Diagnosis(
            key="调控拖累",
            conclusion=(
                f"调控/追投在拖累整体——基础投放 ROI {s_base_roi:.2f} 达标，"
                f"追投调控 ROI 只有 {assist_roi_text}，整体被拉到 {s_total_roi:.2f}"
            ),
            evidence=[
                f"基础投放 ROI {s_base_roi:.2f}（≥目标 {target_text}）",
                f"追投调控 ROI {assist_roi_text}",
                f"整体（含调控/追投）ROI {s_total_roi:.2f}（低于目标）",
                f"被拉低 {s_base_roi - s_total_roi:.2f}",
            ],
            reasoning="基础投放本身达标，说明基础素材和承接没问题；"
                      "整体不达标是调控/追投的量级和效率拖下来的"
                      "（官方：调控量级太大会和主计划抢量、拉低账户 ROI）。",
            ruled_out=["基础投放能力：基础 ROI 已达标，排除"],
            confidence="高",
        ))
        session_fired = True

    if (not session_fired) and plan_splits:
        for item in plan_splits:
            if room_name and room_name not in str(item.get("room") or ""):
                continue
            overall, base_roi = item.get("roi"), item.get("base_roi")
            if overall is None or base_roi is None:
                continue
            if target and base_roi >= target and overall < target:
                out.append(Diagnosis(
                    key="调控拖累",
                    conclusion=f"调控/追投在拖累整体——基础投放 ROI {base_roi:.2f} 达标，整体只有 {overall:.2f}",
                    evidence=[
                        f"基础投放 ROI {base_roi:.2f}（≥目标 {target:.2f}）",
                        f"整体（含调控/追投）ROI {overall:.2f}（低于目标）",
                        f"被拉低 {base_roi - overall:.2f}",
                    ],
                    reasoning="基础投放本身达标，说明素材和承接没问题；"
                              "整体不达标是调控/追投量级过大导致（官方：调控量级太大会和主计划抢量、拉低账户 ROI）。",
                    ruled_out=["基础投放能力：基础 ROI 已达标，排除"],
                    confidence="高",
                ))
                break

    # 规则5：消耗停滞
    if spend_delta is not None and abs(spend_delta) < 1 and metrics.spend > 0:
        out.append(Diagnosis(
            key="消耗停滞",
            conclusion="消耗跑不动——连续周期几乎没有新增消耗",
            evidence=[f"本周期消耗增量 {spend_delta:,.2f}", f"累计消耗 ¥{metrics.spend:,.2f}"],
            reasoning="消耗停滞有两种可能：① 预算/计划层面（撞线、被限流）② 素材层（衰退、跑不动）。"
                      "按官方 SOP，先查预算和计划状态，再查素材。",
            ruled_out=[],
            confidence="中",
        ))

    # 规则6：放量放给了低效流量
    if spend_delta is not None and spend_delta > 0 and conv is not None and conv_low:
        out.append(Diagnosis(
            key="放量质量",
            conclusion="在放量，但放给了低效流量——消耗增加的同时转化率在下滑",
            evidence=[
                f"本期消耗增量 +{spend_delta:,.2f}",
                f"观看成交转化率 {conv:.2f}%（{conv_dev:+.0f}% vs 基线）" if conv_dev is not None else "",
            ],
            reasoning="量增+转化率降 = 新增的流量质量差于存量。"
                      "多半是把量放给了人群池边缘的人，或素材吸引的人群偏泛。",
            ruled_out=[],
            confidence="中",
        ))

    # 规则7：追投占比（官方口径）
    if spend_split:
        basic = float(spend_split.get("basic_spend") or 0)
        assist = float(spend_split.get("assist_spend") or 0)
        if basic + assist > 0:
            ratio = assist / (basic + assist) * 100
            if ratio > 50:
                out.append(Diagnosis(
                    key="调控结构",
                    conclusion=(
                        f"追投/调控占素材口径消耗 {ratio:.1f}%，结构偏重"
                        "（官方建议：控成本追投占账户总消耗约 25%）"
                    ),
                    evidence=[
                        f"追投/调控 ¥{assist:,.2f}（{ratio:.1f}%，分母=素材口径消耗）",
                        f"基础计划 ¥{basic:,.2f}（{100 - ratio:.1f}%）",
                    ],
                    reasoning="官方明确：调控量级太大会和主计划抢量、拉低账户整体 ROI，"
                              "建议控成本追投占账户总消耗 25% 左右。"
                              "（这里的分母是素材口径，和官方账户口径不是同一把尺子，"
                              "看趋势可以，别当成精确倍数。）",
                    ruled_out=[],
                    confidence="高",
                ))

    if not out and roi_low:
        out.append(Diagnosis(
            key="未定位",
            conclusion=f"ROI {roi_text} 未达目标 {target_text}，但未定位到单一主因",
            evidence=["各项指标相对基线的偏离都不显著"],
            reasoning="没有明显异常信号时，可能是目标设得偏高，或需要跨场对比才能看出趋势。",
            ruled_out=[],
            confidence="低",
        ))

    return out
