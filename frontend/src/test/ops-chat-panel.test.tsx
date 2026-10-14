import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

const getOpsChatMessages = vi.fn();
const sendOpsChat = vi.fn();
const generateOpsBriefing = vi.fn();

vi.mock("../lib/api", () => ({
  getOpsChatMessages: (...args: unknown[]) => getOpsChatMessages(...args),
  sendOpsChat: (...args: unknown[]) => sendOpsChat(...args),
  generateOpsBriefing: (...args: unknown[]) => generateOpsBriefing(...args)
}));

import { OpsChatPanel } from "../components/OpsChatPanel";

test("运营助手渲染历史对话（含每日汇报）与执行记录", async () => {
  getOpsChatMessages.mockResolvedValue([
    {
      id: "m1",
      created_at: "2026-10-09T08:05:00+08:00",
      day: "2026-10-09",
      role: "assistant",
      kind: "briefing",
      content: "## 每日运营汇报｜2026-10-08\n\n**一句话结论**：昨日未发现需要处理的问题。"
    },
    { id: "m2", created_at: "2026-10-09T09:00:00+08:00", role: "user", kind: "chat", content: "昨天怎么样" }
  ]);

  render(
    <OpsChatPanel
      jobs={[{ id: "j1", action_name: "update_plan_budget", status: "succeeded", created_at: "2026-10-09T09:10:00+08:00" }]}
    />
  );

  await waitFor(() => expect(getOpsChatMessages).toHaveBeenCalled());
  expect(await screen.findByText("每日运营汇报｜2026-10-08")).toBeInTheDocument();
  expect(screen.getByText("昨天怎么样")).toBeInTheDocument();
  // 执行记录折叠在下面，仍然在页面里
  expect(screen.getByText(/执行记录（1）/)).toBeInTheDocument();
  expect(getOpsChatMessages).toHaveBeenCalledTimes(1);
});

test("收到推送的运营消息会追加到对话里", async () => {
  getOpsChatMessages.mockResolvedValue([]);
  const { rerender } = render(<OpsChatPanel incomingMessage={null} />);
  await waitFor(() => expect(getOpsChatMessages).toHaveBeenCalled());

  rerender(
    <OpsChatPanel incomingMessage={{ id: "push-1", content: "2026-10-08 直播复盘已生成" }} />
  );

  expect(await screen.findByText("2026-10-08 直播复盘已生成")).toBeInTheDocument();
});
