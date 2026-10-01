import { render, screen } from "@testing-library/react";

import { ChatPanel } from "../components/ChatPanel";


test("chat panel automatically receives a completed live review", async () => {
  render(
    <ChatPanel
      incomingMessage={{
        id: "review-1",
        content: "## 直播复盘｜2026-10-01\n\n### 四、明日投放策略\n\n- 保持当前预算"
      }}
    />
  );

  expect(await screen.findByText(/直播复盘｜2026-10-01/)).toBeInTheDocument();
  expect(screen.getByText(/保持当前预算/)).toBeInTheDocument();
});
