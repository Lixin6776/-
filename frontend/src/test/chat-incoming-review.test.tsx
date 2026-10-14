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


test("chat panel renders a material analysis report as a report block", async () => {
  render(
    <ChatPanel
      incomingMessage={{
        id: "material-1",
        content: "## 素材分析报告｜2026-10-01\n\n### 三、新素材制作方向\n\n- 强化痛点表达"
      }}
    />
  );

  const report = await screen.findByText(/素材分析报告｜2026-10-01/);
  // 报表现在渲染成结构化的 Markdown 版式，而不是 <pre> 原始文本
  expect(report.closest(".report-message")).not.toBeNull();
  expect(report.tagName).toBe("H3");
  expect(screen.getByText(/强化痛点表达/)).toBeInTheDocument();
});
