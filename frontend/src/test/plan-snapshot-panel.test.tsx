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

  render(
    <PlanSnapshotPanel
      load={load}
      event={{
        captured_at: "2026-09-30T20:15:00+08:00",
        freshness: "fresh",
        level: "normal",
        reason: "指标正常",
        source: "cdp",
        metrics: {
          roi: 1.86,
          gpm: 3081.75,
          spend: 59246.58,
          gmv: 109600,
          orders: 699,
          online_viewers: 45
        }
      }}
    />
  );

  expect(await screen.findByText("直播大屏")).toBeInTheDocument();
  expect(await screen.findByText(/9,999,999/)).toBeInTheDocument();
  expect(screen.getByText("2.60")).toBeInTheDocument();
  expect(screen.getByText("1.86")).toBeInTheDocument();
  expect(screen.getByText(/59,246.58/)).toBeInTheDocument();
  expect(screen.getByText("45")).toBeInTheDocument();
  expect(screen.getByText("投放中")).toBeInTheDocument();
});
