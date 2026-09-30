import { useEffect, useState } from "react";

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

function sourceLabel(source: string | undefined) {
  if (source === "cdp") return "CDP";
  if (source === "fixture") return "固定样例";
  if (source === "cdp-error") return "CDP 异常";
  return source || "等待数据";
}

export function PlanSnapshotPanel({
  event,
  load = getCurrentPlanSnapshot
}: {
  event?: LiveMonitorEvent | null;
  load?: () => Promise<PlanSnapshot>;
}) {
  const [plan, setPlan] = useState<PlanSnapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const live = event?.metrics;

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      setPlan(await load());
    } catch {
      setError("无法读取当前计划，请确认千川详情页已打开且登录有效。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const metrics = [
    ["综合营销ROI", formatRatio(live?.roi ?? plan?.roi)],
    ["综合成本(元)", formatCurrency(live?.spend ?? plan?.spend)],
    ["净成交金额(元)", formatCurrency(live?.gmv ?? plan?.gmv)],
    ["整体成交订单数", formatNumber(live?.orders ?? plan?.orders)],
    ["GPM(元)", formatCurrency(live?.gpm)],
    ["实时在线人数", formatNumber(live?.online_viewers)]
  ];

  return (
    <section className="byte-live-dashboard">
      <header className="byte-live-header">
        <div className="byte-live-title">
          <span className="byte-live-dot" />
          直播大屏
        </div>
        <div className="byte-live-meta">
          <span>{plan?.name ?? "计划暂无法读取"}</span>
          {plan?.account_name ? <span>{plan.account_name}</span> : null}
          {plan ? <span>{statusLabels[plan.status] ?? plan.status}</span> : null}
          <span>{sourceLabel(event?.source)}</span>
          <span>{event?.captured_at ? new Date(event.captured_at).toLocaleString("zh-CN") : "尚未读取"}</span>
        </div>
        <button className="button-outline byte-refresh-button" type="button" onClick={refresh} disabled={loading}>
          {loading ? "读取中" : "刷新"}
        </button>
      </header>
      {error ? <p className="byte-dashboard-error">{error}</p> : null}
      <div className="byte-live-metrics">
        {metrics.map(([label, value]) => (
          <article className="byte-metric-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
      <footer className="byte-live-footer">
        <span>计划预算：{formatCurrency(plan?.budget)}</span>
        <span>目标ROI：{formatRatio(plan?.roi_goal)}</span>
        <span>数据新鲜度：{event?.freshness ?? "等待中"}</span>
        <span>{event?.reason ?? "等待首次直播监控结果"}</span>
      </footer>
    </section>
  );
}
