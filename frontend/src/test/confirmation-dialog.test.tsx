import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { ConfirmationDialog } from "../components/ConfirmationDialog";


test("confirmation dialog shows diff and profile constraints", () => {
  const onConfirm = vi.fn();
  render(
    <ConfirmationDialog
      preview={{
        action_name: "update_plan_budget",
        target_id: "plan-1",
        normalized_params: { budget: 800 },
        target_name: "计划 A",
        diff: { budget: { before: 1000, after: 800 } },
        blockers: [],
        strategy_profile_version: 3,
        constraints: { daily_budget_max: 5000 },
        expires_at: "2099-09-30T20:25:00+08:00",
        requires_confirmation: true
      }}
      onConfirm={onConfirm}
      onCancel={() => undefined}
    />
  );
  expect(screen.getByText(/计划 A/)).toBeInTheDocument();
  expect(screen.getByText(/1000/)).toBeInTheDocument();
  expect(screen.getByText(/800/)).toBeInTheDocument();
  expect(screen.getByText(/投放策略 v3/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "确认执行" }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
});


test("confirmation dialog disables execution when blockers exist", () => {
  render(
    <ConfirmationDialog
      preview={{
        action_name: "update_plan_budget",
        target_id: "plan-1",
        normalized_params: { budget: 800 },
        target_name: "计划 A",
        diff: { budget: { before: 1000, after: 6000 } },
        blockers: ["目标预算超过 daily_budget_max"],
        strategy_profile_version: 3,
        constraints: { daily_budget_max: 5000 },
        expires_at: "2099-09-30T20:25:00+08:00",
        requires_confirmation: true
      }}
      onConfirm={() => undefined}
      onCancel={() => undefined}
    />
  );
  expect(screen.getByRole("button", { name: "确认执行" })).toBeDisabled();
});

test("destructive confirmation requires explicit acknowledgement", () => {
  render(
    <ConfirmationDialog
      preview={{
        action_name: "delete_plan",
        target_id: "plan-1",
        normalized_params: { reason: "长期亏损" },
        target_name: "计划 A",
        diff: { plan: { before: "plan-1", after: null } },
        blockers: [],
        destructive: true,
        strategy_profile_version: 3,
        constraints: { daily_budget_max: 5000 },
        expires_at: "2099-09-30T20:25:00+08:00",
        requires_confirmation: true
      }}
      onConfirm={() => undefined}
      onCancel={() => undefined}
    />
  );
  expect(screen.getByRole("button", { name: "确认执行" })).toBeDisabled();
  fireEvent.click(screen.getByLabelText("我了解此操作不可逆"));
  expect(screen.getByRole("button", { name: "确认执行" })).toBeEnabled();
});
