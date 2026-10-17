import { useEffect, useState } from "react";

import { getOpsOutcome } from "../lib/api";

type Summary = {
  n: number;
  median_delta: number | null;
  positive_rate: number | null;
  net_effect: number | null;
};

type OpRow = Summary & { operation: string; verdict: string };
type Stratum = {
  label: string;
  treated: Summary;
  control: Summary;
  net_effect: number | null;
  verdict: string;
};

type Payload = {
  baseline: Summary & { operation: string };
  operations: OpRow[];
  velocity_strata: Stratum[];
  window_minutes: number;
  min_sample: number;
  note: string;
};

const VERDICT: Record<string, string> = {
  positive: "✅ 正向",
  negative: "⚠️ 负向",
  neutral: "➖ 中性",
  insufficient: "样本不足"
};

function pct(value: number | null) {
  return value === null ? "--" : `${Math.round(value * 100)}%`;
}

function signed(value: number | null) {
  return value === null ? "--" : `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

/**
 * 《操作反馈表》：你手动做的操作，被数据正向反馈了吗？
 *
 * 口径（先用真实数据自检过）：
 *   净效应 = 操作组中位Δ − 无操作对照组中位Δ（扣掉账户自然漂移）
 *   不是因果结论；n<20 只标"样本不足"。
 */
export function OpsOutcomePanel() {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getOpsOutcome()
      .then((value) => setData(value as Payload))
      .catch(() => setError("读取失败，检查本地服务。"));
  }, []);

  if (error) return <p className="monitor-signal">{error}</p>;
  if (!data) return null;

  return (
    <section className="ops-outcome">
      <h4>操作反馈表（近 {data.window_minutes} 分钟）</h4>
      <p className="monitor-signal">
        基线（无操作时刻）中位Δ <strong>{signed(data.baseline.median_delta)}</strong>
        （n={data.baseline.n}）。净效应 = 操作组 − 这个基线，已扣掉账户自然漂移。
      </p>

      <table>
        <thead>
          <tr>
            <th>操作</th>
            <th>样本</th>
            <th>正反馈率</th>
            <th>净效应</th>
            <th>判定</th>
          </tr>
        </thead>
        <tbody>
          {data.operations.map((row) => (
            <tr key={row.operation}>
              <td>{row.operation}</td>
              <td>{row.n}</td>
              <td>{pct(row.positive_rate)}</td>
              <td>{signed(row.net_effect)}</td>
              <td>{VERDICT[row.verdict] ?? row.verdict}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4>按流速分层（更有用的切法）</h4>
      <table>
        <thead>
          <tr>
            <th>流速</th>
            <th>操作 n</th>
            <th>对照 n</th>
            <th>净效应</th>
            <th>判定</th>
          </tr>
        </thead>
        <tbody>
          {data.velocity_strata.map((row) => (
            <tr key={row.label}>
              <td>{row.label}</td>
              <td>{row.treated.n}</td>
              <td>{row.control.n}</td>
              <td>{signed(row.net_effect)}</td>
              <td>{VERDICT[row.verdict] ?? row.verdict}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="monitor-signal">
        ⚠️ {data.note} 单类样本 &lt; {data.min_sample} 只标"样本不足"，不出结论。
      </p>
    </section>
  );
}
