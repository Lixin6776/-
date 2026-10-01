import { useEffect, useRef, useState } from "react";

import { getCurrentPlanSnapshot } from "../lib/api";
import type { LiveMonitorEvent } from "./LiveMonitorPanel";

export type PlanSnapshot = {
  id: string;
  name: string;
  status: string;
  budget: number;
  roi_goal: number | null;
  account_name?: string | null;
  roi?: number | null;
  spend?: number | null;
  gmv?: number | null;
  orders?: number | null;
};

const statusLabels: Record<string, string> = {
  active: "投放中",
  paused: "已暂停",
  reviewing: "审核中",
  deleted: "已删除",
  ended: "已结束",
  unknown: "状态未知"
};

const numberFormat = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2
});

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? "--" : numberFormat.format(value);
}

function formatCurrency(value: number | null | undefined) {
  return value === null || value === undefined ? "--" : `\u00a5${numberFormat.format(value)}`;
}

function formatRatio(value: number | null | undefined) {
  return value === null || value === undefined ? "--" : value.toFixed(2);
}

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined ? "--" : `${value.toFixed(2)}%`;
}

export function PlanSnapshotPanel({
  event,
  load = getCurrentPlanSnapshot
}: {
  event?: LiveMonitorEvent | null;
  load?: () => Promise<PlanSnapshot>;
}) {
  const [plan, setPlan] = useState<PlanSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const screenRef = useRef<HTMLElement | null>(null);
  const live = event?.metrics;
  const orderCost =
    live?.spend && live?.orders ? live.spend / live.orders : undefined;
  const conversion =
    live?.view_conversion_rate ??
    (live?.views && live.orders ? (live.orders / live.views) * 100 : undefined);

  async function refresh() {
    setLoading(true);
    try {
      setPlan(await load());
    } catch {
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }

  async function enterFullscreen() {
    await screenRef.current?.requestFullscreen?.();
  }

  useEffect(() => {
    void refresh();
  }, []);

  const heroMetrics = [
    ["综合成本(元)", formatCurrency(live?.spend ?? plan?.spend)],
    ["综合营销ROI", formatRatio(live?.roi ?? plan?.roi)],
    ["净成交金额(元)", formatCurrency(live?.gmv ?? plan?.gmv)]
  ];
  const secondaryMetrics = [
    ["整体成交订单数", formatNumber(live?.orders ?? plan?.orders)],
    ["GPM(元)", formatCurrency(live?.gpm)],
    ["观看成交转化率", formatPercent(conversion)],
    ["整体成交订单成本(元)", formatCurrency(orderCost)],
    ["实时在线人数", formatNumber(live?.online_viewers)],
    ["曝光观看率(次数)", formatPercent(live?.exposure_view_rate)],
    ["直播间整体观看人数", formatNumber(live?.views)]
  ];
  const funnel = [
    ["直播间整体曝光次数", formatNumber(live?.exposure_count)],
    ["直播间观看次数", formatNumber(live?.view_count ?? live?.views)],
    ["商品点击次数", formatNumber(live?.product_clicks)],
    ["成交订单数", formatNumber(live?.orders)]
  ];
  const channels = ["短视频及图文引流", "搜索", "直播推荐", "抖音商城推荐", "其他"];

  return (
    <section className="qianchuan-live-screen" ref={screenRef}>
      <header className="qls-topbar">
        <div className="qls-brand">
          <span className="qls-douyin">抖</span>
          <strong>抖音电商</strong>
          <i />
          <span className="qls-qianchuan">巨量千川</span>
          <span className="qls-screen-title">直播大屏</span>
        </div>
        <div className="qls-actions">
          <span>{plan?.account_name ?? "账户暂无法读取"}</span>
          <button type="button" onClick={refresh} disabled={loading}>
            {loading ? "刷新中" : "刷新数据"}
          </button>
          <button type="button" onClick={enterFullscreen}>全屏</button>
        </div>
      </header>
      <div className="qls-announcement">
        <span>公告</span>
        全域直播大屏已接入本地 AI 助手，数据仅用于只读监控与分析
      </div>
      <div className="qls-layout">
        <main className="qls-main">
          <section className="qls-hero">
            {heroMetrics.map(([label, value]) => (
              <article className="qls-hero-card" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </article>
            ))}
            <div className="qls-plan-meta">
              <span>{plan?.name ?? "计划暂无法读取"}</span>
              <span>{plan ? statusLabels[plan.status] ?? plan.status : "状态未知"}</span>
              <span>{event?.captured_at ? new Date(event.captured_at).toLocaleString("zh-CN") : "尚未读取"}</span>
            </div>
          </section>
          <section className="qls-secondary">
            {secondaryMetrics.map(([label, value]) => (
              <article key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </article>
            ))}
          </section>
          <section className="qls-trend">
            <div className="qls-trend-head">
              <div>
                <button className="active" type="button">整体趋势</button>
                <button type="button">素材表现</button>
              </div>
              <div className="qls-chart-tools">
                <span>5分钟粒度</span>
                <span>筛选</span>
              </div>
            </div>
            <div className="qls-legend">
              {["综合成本", "净成交金额", "综合ROI", "消耗", "整体成交金额", "整体支付ROI"].map((item) => (
                <span key={item}><i />{item}</span>
              ))}
            </div>
            <div className="qls-chart-placeholder">
              <div className="qls-gridlines" />
              <p>等待监控趋势数据，至少运行两个监控周期后显示曲线。</p>
            </div>
          </section>
        </main>
        <aside className="qls-side">
          <section className="qls-side-card">
            <header><h3>成交渠道构成</h3><span>观看次数</span></header>
            <div className="qls-channel-body">
              <div className="qls-donut" />
              <ul>
                {channels.map((item) => <li key={item}><i />{item}<b>--</b></li>)}
              </ul>
            </div>
          </section>
          <section className="qls-side-card">
            <header><h3>直播间核心漏斗</h3></header>
            <ul className="qls-funnel">
              {funnel.map(([label, value]) => (
                <li key={label}><span>{label}</span><strong>{value}</strong></li>
              ))}
            </ul>
          </section>
          <section className="qls-side-card qls-comments">
            <header><h3>直播实时评论</h3><span>直播画面</span></header>
            <p>暂无直播评论数据</p>
          </section>
        </aside>
      </div>
      <footer className="qls-footer">
        <span>计划预算：{formatCurrency(plan?.budget)}</span>
        <span>目标ROI：{formatRatio(plan?.roi_goal)}</span>
        <span>数据新鲜度：{event?.freshness ?? "等待中"}</span>
        <span>{event?.reason ?? "等待首次直播监控结果"}</span>
      </footer>
    </section>
  );
}
