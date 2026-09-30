type Suggestion = {
  id: string;
  suggestion_type: string;
  proposed_change: Record<string, unknown>;
  evidence: Record<string, unknown>;
  confidence: string;
  status: string;
};

export function StrategySuggestionCard({
  suggestion,
  onAccept,
  onReject
}: {
  suggestion: Suggestion;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
}) {
  return (
    <article className="panel strategy-suggestion-card">
      <p className="eyebrow">{suggestion.suggestion_type}</p>
      <h3>策略优化建议</h3>
      <pre>{JSON.stringify(suggestion.proposed_change, null, 2)}</pre>
      <p>置信度：{suggestion.confidence}</p>
      <div className="decision-actions">
        <button className="button-outline" type="button" onClick={() => onReject(suggestion.id)}>
          拒绝
        </button>
        <button className="button-primary" type="button" onClick={() => onAccept(suggestion.id)}>
          接受为草稿
        </button>
      </div>
    </article>
  );
}