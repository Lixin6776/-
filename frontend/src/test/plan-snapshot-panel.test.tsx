import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { PlanSnapshotPanel } from "../components/PlanSnapshotPanel";


test("plan snapshot panel displays read-only plan data", async () => {
  const load = vi.fn().mockResolvedValue({
    id: "1876023119718580",
    name: "计划 1876023119718580",
    status: "active",
    budget: 9999999,
    roi_goal: 2.6
  });

  render(<PlanSnapshotPanel load={load} />);

  expect(await screen.findByText(/9,999,999/)).toBeInTheDocument();
  expect(screen.getByText("2.60")).toBeInTheDocument();
  expect(screen.getByText("投放中")).toBeInTheDocument();
});
