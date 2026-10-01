export type MaterialAnalysis = {
  id: string;
  date: string;
  created_at: string;
  report_markdown: string;
};

export function MaterialAnalysisList({
  analyses,
  onGenerate
}: {
  analyses: MaterialAnalysis[];
  onGenerate?: () => void;
}) {
  return (
    <div className="material-analysis-list">
      <button className="button-primary" type="button" onClick={onGenerate}>
        立即生成素材分析
      </button>
      {analyses.length ? (
        analyses.map((analysis) => (
          <article className="material-analysis-item" key={analysis.id}>
            <header>
              <strong>{analysis.date} 素材分析</strong>
              <time>{new Date(analysis.created_at).toLocaleString("zh-CN")}</time>
            </header>
            <pre>{analysis.report_markdown}</pre>
          </article>
        ))
      ) : (
        <p className="empty-state">每天 08:00 自动生成素材分析和新素材制作方向。</p>
      )}
    </div>
  );
}
