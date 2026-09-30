import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import App from "../App";
import { ChatPanel } from "../components/ChatPanel";

vi.mock("../lib/api", () => ({
  getActiveProfile: vi.fn().mockResolvedValue({
    version: 9,
    business_direction: "稳定放量",
    primary_objective: "在 ROI >= 2.5 的前提下提升成交额",
    hard_constraints: { daily_budget_max: 5000 },
    data_time: "2026-09-30T20:15:00+08:00",
    freshness: "fresh"
  }),
  sendChat: vi.fn().mockResolvedValue({ kind: "analysis", message: "当前 ROI 为 2.5。" }),
  connectMonitor: vi.fn().mockReturnValue(() => undefined)
}));

test("app loads the active profile from the local API", async () => {
  render(<App />);
  expect(await screen.findByText(/策略画像 v9/)).toBeInTheDocument();
});

test("chat panel renders the assistant response", async () => {
  const onSend = vi.fn().mockResolvedValue({ message: "当前 ROI 为 2.5。" });
  render(<ChatPanel onSend={onSend} />);
  fireEvent.change(screen.getByLabelText("输入投放问题"), { target: { value: "看看 ROI" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  expect(await screen.findByText("当前 ROI 为 2.5。")).toBeInTheDocument();
  expect(onSend).toHaveBeenCalledWith("看看 ROI");
});

test("chat panel exposes a structured action preview for confirmation", async () => {
  const onSend = vi.fn().mockResolvedValue({
    message: "已生成预算修改预览。",
    preview: {
      action_name: "update_plan_budget",
      target_name: "计划 A",
      diff: { budget: { before: 1000, after: 800 } },
      blockers: [],
      strategy_profile_version: 3,
      expires_at: "2026-09-30T20:25:00+08:00",
      requires_confirmation: true
    }
  });
  const onOpenConfirmation = vi.fn();
  render(<ChatPanel onSend={onSend} onOpenConfirmation={onOpenConfirmation} />);
  fireEvent.change(screen.getByLabelText("输入投放问题"), { target: { value: "预算改成800" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  expect(await screen.findByText("计划 A")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "查看并确认" }));
  expect(onOpenConfirmation).toHaveBeenCalledTimes(1);
});
