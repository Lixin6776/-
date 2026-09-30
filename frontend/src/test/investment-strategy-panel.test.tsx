import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { InvestmentStrategyPanel } from "../components/InvestmentStrategyPanel";


test("investment strategy panel creates an active strategy", async () => {
  const save = vi.fn().mockResolvedValue({ id: "p1", version: 1, active: true });
  const onCreated = vi.fn();

  render(<InvestmentStrategyPanel save={save} onCreated={onCreated} />);

  fireEvent.click(screen.getByRole("button", { name: "创建并激活投放策略" }));

  await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
  expect(save.mock.calls[0][0]).toMatchObject({
    name: "默认策略",
    business_direction: "稳定放量",
    hard_constraints: { daily_budget_max: 5000 },
    monitoring_config: { interval_minutes: 5 }
  });
  expect(onCreated).toHaveBeenCalledWith({ id: "p1", version: 1, active: true });
  expect(await screen.findByText(/投放策略 v1 已激活/)).toBeInTheDocument();
});
