import { useEffect, useState } from "react";

import { getCurrentPlanSnapshot } from "../lib/api";

export type PlanSnapshot = {
  id: string;
  name: string;
  status: string;
  budget: number;
  roi_goal: number | null;
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

export function PlanSnapshotPanel({
  load = getCurrentPlanSnapshot
}: {
  load?: () => Promise<PlanSnapshot>;
}) {
  const [plan, setPlan] = useState<PlanSnapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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

  return (
    <section className="panel plan-snapshot-panel">
      <div className="panel-heading plan-snapshot-heading">
        <div>
          <p className="eyebrow">Read-only plan</p>
          <h2>当前计划快照</h2>
        </div>
        <button className="button-outline" type="button" onClick={refresh} disabled={loading}>
          {loading ? "读取中" : "刷新"}
        </button>
      </div>
      {error ? <p className="monitor-signal monitor-signal-action">{error}</p> : null}
      {plan ? (
        <>
          <div className="monitor-meta">
            <span>{plan.name}</span>
            <span>{statusLabels[plan.status] ?? plan.status}</span>
          </div>
          <div className="metric-grid">
            <article className="metric-card">
              <span>预算</span>
              <strong>¥{numberFormat.format(plan.budget)}</strong>
            </article>
            <article className="metric-card">
              <span>ROI 目标</span>
              <strong>{plan.roi_goal === null ? "--" : plan.roi_goal.toFixed(2)}</strong>
            </article>
          </div>
        </>
      ) : null}
    </section>
  );
}
