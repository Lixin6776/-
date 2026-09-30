const metrics = [
  ["ROI", "2.50"],
  ["消耗", "¥400"],
  ["成交", "¥1,000"],
  ["GPM", "¥1,000"],
  ["在线人数", "120"]
];

export function LiveMonitorPanel() {
  return (
    <section className="panel live-panel">
      <div className="panel-heading">
        <p className="eyebrow">Live monitor · 5 min</p>
        <h2>计划与直播间</h2>
      </div>
      <div className="metric-grid">
        {metrics.map(([label, value]) => (
          <article className="metric-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}