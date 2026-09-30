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

  const rows = [
    ["支付ROI", formatRatio(live?.roi ?? plan?.roi)],
    ["消耗", formatCurrency(live?.spend ?? plan?.spend)],
    ["成交", formatCurrency(live?.gmv ?? plan?.gmv)],
    ["订单", formatNumber(live?.orders ?? plan?.orders)],
    ["GPM", formatCurrency(live?.gpm)],
    ["在线人数", formatNumber(live?.online_viewers)],
    ["计划预算", formatCurrency(plan?.budget)],
    ["目标ROI", formatRatio(plan?.roi_goal)]
  ];

  return (
    <section className="panel plan-snapshot-panel live-dashboard-panel">
      <div className="panel-heading plan-snapshot-heading">
        <div>
          <p className="eyebrow">Live dashboard</p>
          <h2>直播大屏</h2>
        </div>
        <button className="button-outline" type="button" onClick={refresh} disabled={loading}>
          {loading ? "读取中" : "刷新"}
        </button>
      </div>
      <div className="monitor-meta">
        <span>{plan?.name ?? "计划暂无法读取"}</span>
        {plan?.account_name ? <span>{plan.account_name}</span> : null}
        {plan ? <span>{statusLabels[plan.status] ?? plan.status}</span> : null}
        <span>{sourceLabel(event?.source)}</span>
        <span>数据新鲜度：{event?.freshness ?? "等待中"}</span>
        <time>{event?.captured_at ? new Date(event.captured_at).toLocaleString("zh-CN") : "尚未读取"}</time>
      </div>
      {error ? <p className="monitor-signal monitor-signal-action">{error}</p> : null}
      <div className="metric-grid">
        {rows.map(([label, value]) => (
          <article className="metric-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
      <p className={`monitor-signal monitor-signal-${event?.level ?? "normal"}`}>
        {event?.reason ?? "等待首次直播监控结果"}
      </p>
    </section>
  );
}
