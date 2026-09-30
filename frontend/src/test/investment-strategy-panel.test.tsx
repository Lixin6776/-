import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { InvestmentStrategyPanel } from "../components/InvestmentStrategyPanel";


test("investment strategy panel creates an active strategy", async () => {
  const save = vi.fn().mockResolvedValue({ id: "p1", version: 1, active: true });
  const onCreated = vi.fn();

  render(<InvestmentStrategyPanel save={save} onCreated={onCreated} />);

  fireEvent.click(screen.getByRole("button", { name: "创建并激活投放策略" }));

  await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
  expect(screen.getByLabelText("ROI目标")).toHaveValue(2.5);
  expect(screen.queryByLabelText("投放策略名称")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("策略大方向")).not.toBeInTheDocument();
  expect(save.mock.calls[0][0]).toMatchObject({
    name: "默认投放策略",
    business_direction: "ROI目标 2.5",
    hard_constraints: { daily_budget_max: 5000, roi_target: 2.5 },
    monitoring_config: { interval_minutes: 5 }
  });
  expect(onCreated).toHaveBeenCalledWith({ id: "p1", version: 1, active: true });
  expect(await screen.findByText(/投放策略 v1 已激活/)).toBeInTheDocument();
});
