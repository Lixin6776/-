type Decision = {
  id: string;
  title: string;
  reason: string;
  confidence: string;
};

export function DecisionPanel({
  decisions,
  onConfirm,
  onReject
}: {
  decisions: Decision[];
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
}) {
  return (
    <section className="panel decision-panel">
      <div className="panel-heading">
        <p className="eyebrow">Human in the loop</p>
        <h2>待确认建议</h2>
      </div>
      {decisions.length === 0 ? (
        <p className="empty-state">当前没有待确认操作。</p>
      ) : (
        decisions.map((decision) => (
          <article key={decision.id} className="decision-card">
            <h3>{decision.title}</h3>
            <p>{decision.reason}</p>
            <small>置信度：{decision.confidence}</small>
            <div className="decision-actions">
              <button className="button-outline" onClick={() => onReject(decision.id)}>
                暂不执行
              </button>
              <button className="button-primary" onClick={() => onConfirm(decision.id)}>
                确认执行建议
              </button>
            </div>
          </article>
        ))
      )}
    </section>
  );
}