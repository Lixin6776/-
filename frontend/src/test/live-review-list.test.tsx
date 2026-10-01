import { render, screen } from "@testing-library/react";

import { LiveReviewList } from "../components/LiveReviewList";


test("live review list renders report and next-day strategy", () => {
  render(
    <LiveReviewList
      reviews={[
        {
          id: "r1",
          date: "2026-10-01",
          created_at: "2026-10-01T23:30:00+08:00",
          ended_at: "2026-10-01T23:30:00+08:00",
          report_markdown: "## 直播复盘｜2026-10-01\n\n### 四、明日投放策略\n\n- 保持预算"
        }
      ]}
    />
  );

  expect(screen.getByText(/2026-10-01 直播复盘/)).toBeInTheDocument();
  expect(screen.getByText(/明日投放策略/)).toBeInTheDocument();
});
