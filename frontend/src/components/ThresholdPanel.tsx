import { useEffect, useState } from "react";

import { createStrategyProfile, getActiveProfile } from "../lib/api";

type Profile = {
  version: number;
  name: string;
  business_direction: string;
  primary_objective: string;
  secondary_objectives?: string[];
  hard_constraints?: Record<string, unknown>;
  monitoring_config?: Record<string, unknown>;
  allowed_actions?: string[];
  notification_policy?: Record<string, unknown>;
};

/** 可自定义的判断标准（留空 = 自动） */
const FIELDS: Array<{ key: string; label: string; unit: string; hint: string }> = [
  { key: "exposure_view_rate", label: "曝光观看率", unit: "%", hint: "低于它算「进人不行」" },
  { key: "view_conversion_rate", label: "观看成交转化率", unit: "%", hint: "低于它算「承接不行」" },
  { key: "gpm", label: "GPM", unit: "元", hint: "低于它算「单位观看产出不够」" },
  { key: "cpm", label: "CPM", unit: "元", hint: "高于它算「拿量成本偏高」" },
  { key: "assist_share", label: "追投/调控占比", unit: "%", hint: "高于它算「结构偏重」（官方建议约 25%）" },
];

/**
 * 判断标准（阈值）：你来定。
 * 留空 = 自动（先用本账户历史分位，样本不足再退回通用参考线）。
 * 保存 = 生成策略新版本（可回溯），不会悄悄改掉旧版本。
 */
export function ThresholdPanel() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    getActiveProfile()
      .then((p) => {
        const data = p as Profile;
        setProfile(data);
        const saved = (data.hard_constraints?.thresholds || {}) as Record<string, unknown>;
        const next: Record<string, string> = {};
        for (const field of FIELDS) {
          const value = saved[field.key];
          next[field.key] = typeof value === "number" ? String(value) : "";
        }
        setValues(next);
      })
      .catch(() => setNotice("读取当前策略失败，检查本地服务是否在跑。"));
  }, []);

  async function handleSave() {
    if (!profile) return;
    setBusy(true);
    setNotice("");
    const thresholds: Record<string, number> = {};
    for (const field of FIELDS) {
      const raw = (values[field.key] || "").trim();
      if (!raw) continue;
      const num = Number(raw);
      if (!Number.isFinite(num)) {
        setNotice(`${field.label} 填的不是数字：${raw}`);
        setBusy(false);
        return;
      }
      thresholds[field.key] = num;
    }
    try {
      const saved = (await createStrategyProfile({
        name: profile.name,
        business_direction: profile.business_direction,
        primary_objective: profile.primary_objective,
        secondary_objectives: profile.secondary_objectives || [],
        hard_constraints: { ...(profile.hard_constraints || {}), thresholds },
        monitoring_config: profile.monitoring_config || { interval_minutes: 5 },
        allowed_actions: profile.allowed_actions || [],
        notification_policy: profile.notification_policy || { dedupe_minutes: 10 }
      })) as Profile;
      setProfile(saved);
      setNotice(`已保存为策略 v${saved.version}（旧的保留，可回溯）`);
    } catch {
      setNotice("保存失败，检查本地服务。");
    } finally {
      setBusy(false);
    }
  }

  function resetAll() {
    const next: Record<string, string> = {};
    for (const field of FIELDS) next[field.key] = "";
    setValues(next);
    setNotice("已清空（点「保存」后生效：全部改回自动）");
  }

  return (
    <section className="threshold-panel">
      <p className="eyebrow">Decision rules</p>
      <h3>判断标准</h3>
      <p className="ops-role-desc">
        这些是判断"某个指标好不好"的线。**填了就用你填的**；留空则自动：
        先用本账户历史分位，样本不足再退回通用参考线（并在报告里标明"非本账户"）。
        {profile ? ` 当前策略 v${profile.version}。` : ""}
      </p>

      <table className="threshold-table">
        <thead>
          <tr>
            <th>指标</th>
            <th>你设定的值</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          {FIELDS.map((field) => (
            <tr key={field.key}>
              <td>{field.label}</td>
              <td>
                <input
                  aria-label={field.label}
                  inputMode="decimal"
                  placeholder="留空=自动"
                  value={values[field.key] ?? ""}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [field.key]: event.target.value }))
                  }
                />
                <span className="threshold-unit">{field.unit}</span>
              </td>
              <td>{field.hint}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="live-watch-actions">
        <button className="button-outline" type="button" onClick={handleSave} disabled={busy || !profile}>
          {busy ? "保存中" : "保存为新版本"}
        </button>
        <button className="button-outline" type="button" onClick={resetAll} disabled={busy}>
          全部改回自动
        </button>
      </div>

      {notice ? <p className="monitor-signal">{notice}</p> : null}
      <p className="monitor-signal">
        说明：ROI 目标不在这里设——它跟着千川计划里的「综合营销ROI目标」走，避免盯盘和复盘用到两个目标。
      </p>
    </section>
  );
}
