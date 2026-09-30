import { render, screen } from "@testing-library/react";

import { LiveMonitorPanel } from "../components/LiveMonitorPanel";


test("live monitor renders CDP metrics and action state", () => {
  render(
    <LiveMonitorPanel
      event={{
        captured_at: "2026-09-30T20:15:00+08:00",
        freshness: "fresh",
        level: "action",
        reason: "ROI 显著下降",
        source: "cdp",
        metrics: {
          roi: 2,
          gpm: 3016.67,
          spend: 4968.02,
          gmv: 9948,
          orders: 66,
          online_viewers: 128
        }
      }}
    />
  );

  expect(screen.getByText("2.00")).toBeInTheDocument();
  expect(screen.getByText(/4,968\.02/)).toBeInTheDocument();
  expect(screen.getByText(/3,016\.67/)).toBeInTheDocument();
  expect(screen.getByText("128")).toBeInTheDocument();
  expect(screen.getByText(/建议行动/)).toBeInTheDocument();
  expect(screen.getByText(/ROI 显著下降/)).toBeInTheDocument();
  expect(screen.getByText("CDP")).toBeInTheDocument();
});
