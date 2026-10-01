import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import App from "../App";
import { ChatPanel } from "../components/ChatPanel";

vi.mock("../lib/api", () => ({
  createStrategyProfile: vi.fn().mockResolvedValue({
    id: "p1",
    version: 10,
    active: true,
    name: "默认策略",
    business_direction: "稳定放量",
    primary_objective: "ROI >= 2.5",
    hard_constraints: {}
  }),
  getActiveProfile: vi.fn().mockResolvedValue({
    version: 9,
    business_direction: "稳定放量",
    primary_objective: "在 ROI >= 2.5 的前提下提升成交额",
    hard_constraints: { daily_budget_max: 5000 },
    data_time: "2026-09-30T20:15:00+08:00",
    freshness: "fresh"
  }),
  sendChat: vi.fn().mockResolvedValue({ kind: "analysis", message: "当前 ROI 为 2.5。" }),
  getExecutionJobs: vi.fn().mockResolvedValue([]),
  getApiConnectionStatus: vi.fn().mockResolvedValue({ configured: false, provider_preference: "cdp" }),
  getLearningCases: vi.fn().mockResolvedValue([]),
  getLearningEvaluations: vi.fn().mockResolvedValue([]),
  getLiveReviews: vi.fn().mockResolvedValue([]),
  getLearningSuggestions: vi.fn().mockResolvedValue([]),
  decideLearningSuggestion: vi.fn().mockResolvedValue({ status: "accepted" }),
  createActionConfirmation: vi.fn().mockResolvedValue({ id: "c1" }),  executeActionConfirmation: vi.fn().mockResolvedValue({ id: "j1", status: "pending" }),
  connectMonitor: vi.fn().mockReturnValue(() => undefined),
  getLlmConnectionStatus: vi.fn().mockResolvedValue({
    configured: false,
    base_url: "https://api.deepseek.com",
    model: "deepseek-chat",
    api_key_configured: false
  }),
  saveLlmConnection: vi.fn().mockResolvedValue({
    configured: true,
    base_url: "https://api.deepseek.com",
    model: "deepseek-chat",
    api_key_configured: true
  }),
  testLlmConnection: vi.fn().mockResolvedValue({ ok: true, message: "大模型连接成功" }),
  getCurrentPlanSnapshot: vi.fn().mockResolvedValue({
    id: "plan-1",
    name: "计划 plan-1",
    status: "active",
    budget: 1000,
    roi_goal: 2.6,
    roi: 1.87,
    spend: 60778.54,
    gmv: 113586.29,
    orders: 747
  })
}));

test("app loads the active profile from the local API", async () => {
  render(<App />);
  expect(await screen.findByText(/投放策略 v9/)).toBeInTheDocument();
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


test("left navigation opens a floating tool window", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "大模型" }));
  expect(await screen.findByRole("dialog", { name: "大模型" })).toBeInTheDocument();
  expect(await screen.findByText("DeepSeek 大模型")).toBeInTheDocument();
});
