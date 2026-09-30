type Evaluation = {
  sample_size: number;
  confidence: string;
  verdict: string;
  evidence: Record<string, unknown>;
};

const confidenceLabels: Record<string, string> = {
  low: "低置信度",
  medium: "中置信度",
  high: "高置信度"
};

const verdictLabels: Record<string, string> = {
  beneficial: "有效",
  harmful: "有害",
  neutral: "中性",
  insufficient_data: "样本不足"
};

export function StrategyEvaluationPanel({ evaluation }: { evaluation: Evaluation }) {
  return (
    <section className="panel strategy-evaluation-panel">
      <div className="panel-heading">
        <p className="eyebrow">Strategy evaluation</p>
        <h2>策略评估</h2>
      </div>
      <div className="metric-grid">
        <article className="metric-card">
          <span>样本量</span>
          <strong>{evaluation.sample_size}</strong>
        </article>
        <article className="metric-card">
          <span>{confidenceLabels[evaluation.confidence] ?? evaluation.confidence}</span>
          <strong>{verdictLabels[evaluation.verdict] ?? evaluation.verdict}</strong>
        </article>
      </div>
      <pre>{JSON.stringify(evaluation.evidence, null, 2)}</pre>
    </section>
  );
}