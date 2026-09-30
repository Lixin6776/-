import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { PlanSnapshotPanel } from "../components/PlanSnapshotPanel";


test("plan snapshot panel displays read-only plan data", async () => {
  const load = vi.fn().mockResolvedValue({
    id: "1876023119718580",
    name: "计划 1876023119718580",
    status: "active",
    budget: 9999999,
    roi_goal: 2.6,
    roi: 1.87,
    spend: 60778.54,
    gmv: 113586.29,
    orders: 747
  });

  render(<PlanSnapshotPanel load={load} />);

  expect(await screen.findByText(/9,999,999/)).toBeInTheDocument();
  expect(screen.getByText("2.60")).toBeInTheDocument();
  expect(screen.getByText("1.87")).toBeInTheDocument();
  expect(screen.getByText(/60,778.54/)).toBeInTheDocument();
  expect(screen.getByText(/113,586.29/)).toBeInTheDocument();
  expect(screen.getByText("747")).toBeInTheDocument();
  expect(screen.getByText("投放中")).toBeInTheDocument();
});
