import { FormEvent, useState } from "react";

import { createStrategyProfile } from "../lib/api";

const DEFAULT_ACTIONS = [
  "pause_plan",
  "enable_plan",
  "update_plan_budget",
  "create_plan",
  "copy_plan",
  "delete_plan",
  "edit_plan",
  "update_plan_bid",
  "update_targeting",
  "update_schedule",
  "bind_existing_material",
  "unbind_existing_material"
];

type ProfilePayload = {
  name: string;
  business_direction: string;
  primary_objective: string;
  secondary_objectives?: string[];
  hard_constraints?: Record<string, unknown>;
  monitoring_config?: Record<string, unknown>;
  allowed_actions?: string[];
  notification_policy?: Record<string, unknown>;
};

type Props = {
  save?: (profile: ProfilePayload) => Promise<Record<string, unknown>>;
  onCreated?: (profile: Record<string, unknown>) => void;
};

export function StrategyProfilePanel({ save = createStrategyProfile, onCreated }: Props) {
  const [name, setName] = useState("默认策略");
  const [direction, setDirection] = useState("稳定放量");
  const [objective, setObjective] = useState("在 ROI >= 2.5 的前提下提升成交额");
  const [dailyBudgetMax, setDailyBudgetMax] = useState("5000");
  const [interval, setInterval] = useState("5");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const created = await save({
        name,
        business_direction: direction,
        primary_objective: objective,
        secondary_objectives: [],
        hard_constraints: { daily_budget_max: Number(dailyBudgetMax) },
        monitoring_config: { interval_minutes: Number(interval) },
        allowed_actions: DEFAULT_ACTIONS,
        notification_policy: { dedupe_minutes: 10 }
      });
      onCreated?.(created);
      setMessage(`策略画像 v${created.version} 已激活。`);
    } catch {
      setMessage("策略画像保存失败，请检查参数。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel strategy-profile-panel">
      <div className="panel-heading">
        <p className="eyebrow">Strategy profile</p>
        <h2>策略画像</h2>
      </div>
      <form className="action-form" onSubmit={submit}>
        <label>
          画像名称
          <input aria-label="策略画像名称" value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          大方向
          <input
            aria-label="策略大方向"
            value={direction}
            onChange={(event) => setDirection(event.target.value)}
            required
          />
        </label>
        <label>
          主目标
          <textarea
            aria-label="策略主目标"
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            rows={3}
            required
          />
        </label>
        <label>
          日预算上限
          <input
            aria-label="日预算上限"
            type="number"
            min="1"
            value={dailyBudgetMax}
            onChange={(event) => setDailyBudgetMax(event.target.value)}
            required
          />
        </label>
        <label>
          监控间隔（分钟）
          <input
            aria-label="监控间隔"
            type="number"
            min="1"
            value={interval}
            onChange={(event) => setInterval(event.target.value)}
            required
          />
        </label>
        <button className="button-primary" type="submit" disabled={busy}>
          {busy ? "保存中" : "创建并激活画像"}
        </button>
      </form>
      {message ? <p className="monitor-signal">{message}</p> : null}
    </section>
  );
}
