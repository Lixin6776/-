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
    </section>
  );
}
