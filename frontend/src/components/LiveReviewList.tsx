export type LiveReview = {
  id: string;
  date: string;
  created_at: string;
  ended_at: string;
  report_markdown: string;
};

export function LiveReviewList({ reviews }: { reviews: LiveReview[] }) {
  if (!reviews.length) {
    return <p className="empty-state">直播结束后会自动生成复盘报告和明日投放策略。</p>;
  }

  return (
    <div className="live-review-list">
      {reviews.map((review) => (
        <article className="live-review-item" key={review.id}>
          <header>
            <strong>{review.date} 直播复盘</strong>
            <time>{new Date(review.created_at).toLocaleString("zh-CN")}</time>
          </header>
          <pre>{review.report_markdown}</pre>
        </article>
      ))}
    </div>
  );
}
