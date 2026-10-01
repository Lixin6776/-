export type LiveMonitorEvent = {
  captured_at: string;
  freshness: string;
  level: "normal" | "watch" | "action" | string;
  reason: string;
  source: string;
  live_ended?: boolean;
  review?: { id: string; date: string; created_at: string; ended_at: string; report_markdown: string } | null;
  metrics: {
    roi: number | null;
    gpm: number | null;
    spend: number;
    gmv: number;
    orders: number;
    online_viewers: number;
    views?: number | null;
    exposure_count?: number | null;
    view_count?: number | null;
    product_clicks?: number | null;
    view_conversion_rate?: number | null;
    exposure_view_rate?: number | null;
  };
};

type Props = {
  event?: LiveMonitorEvent | null;
};

const numberFormat = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2
});

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? "--" : numberFormat.format(value);
}

function formatRatio(value: number | null | undefined) {
  return value === null || value === undefined ? "--" : value.toFixed(2);
}

function formatCurrency(value: number | null | undefined) {
  return value === null || value === undefined
    ? "--"
    : `\u00a5${numberFormat.format(value)}`;
}

function levelLabel(level: string | undefined) {
  if (level === "action") return "建议行动";
  if (level === "watch") return "观察";
  return "正常";
}

function sourceLabel(source: string | undefined) {
  if (source === "cdp") return "CDP";
  if (source === "fixture") return "固定样例";
  if (source === "cdp-error") return "CDP 异常";
  return source || "等待数据";
}

export function LiveMonitorPanel({ event }: Props) {
  const metrics = event?.metrics;
  const rows = [
    ["ROI", formatRatio(metrics?.roi)],
    ["消耗", formatCurrency(metrics?.spend)],
    ["成交", formatCurrency(metrics?.gmv)],
    ["GPM", formatCurrency(metrics?.gpm)],
    ["在线人数", formatNumber(metrics?.online_viewers)],
    ["订单", formatNumber(metrics?.orders)]
  ];

  return (
    <section className="panel live-panel">
      <div className="panel-heading">
        <p className="eyebrow">Live monitor · 5–10 min</p>
        <h2>计划与直播间</h2>
      </div>
      <div className="monitor-meta">
        <span>{sourceLabel(event?.source)}</span>
        <span>数据新鲜度：{event?.freshness ?? "等待中"}</span>
        <time>{event?.captured_at ? new Date(event.captured_at).toLocaleString("zh-CN") : "尚未读取"}</time>
      </div>
      <div className="metric-grid">
        {rows.map(([label, value]) => (
          <article className="metric-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
      <p className={ `monitor-signal monitor-signal-${event?.level ?? "normal"}` }>
        {levelLabel(event?.level)} · {event?.reason ?? "等待首次监控结果"}
      </p>
    </section>
  );
}
