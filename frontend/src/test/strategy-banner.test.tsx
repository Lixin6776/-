import { fireEvent, render, screen } from "@testing-library/react";

import { DecisionPanel } from "../components/DecisionPanel";
import { StrategyBanner } from "../components/StrategyBanner";

test("strategy banner is always visible with profile data", () => {
  render(
    <StrategyBanner
      profile={{
        version: 3,
        business_direction: "稳定放量",
        primary_objective: "ROI >= 2.5 且提升成交额",
        hard_constraints: { daily_budget_max: 5000 },
        data_time: "2026-09-30T20:15:00+08:00",
        freshness: "fresh"
      }}
    />
  );
  expect(screen.getByText(/策略画像 v3/)).toBeInTheDocument();
  expect(screen.getByText(/ROI >= 2.5/)).toBeInTheDocument();
  expect(screen.getByText(/数据最新/)).toBeInTheDocument();
});

test("decision panel requires an explicit confirmation click", () => {
  const confirmed: string[] = [];
  render(
    <DecisionPanel
      decisions={[
        {
          id: "d1",
          title: "计划 A 降预算",
          reason: "ROI 连续下降",
          confidence: "medium"
        }
      ]}
      onConfirm={(id) => confirmed.push(id)}
      onReject={() => undefined}
    />
  );
  expect(confirmed).toEqual([]);
  fireEvent.click(screen.getByRole("button", { name: "确认执行建议" }));
  expect(confirmed).toEqual(["d1"]);
});