import { render, screen } from "@testing-library/react";

import { ExecutionTimeline } from "../components/ExecutionTimeline";


test("execution timeline shows statuses with text labels", () => {
  render(
    <ExecutionTimeline
      jobs={[
        {
          id: "job-1",
          action_name: "pause_plan",
          status: "verifying",
          created_at: "2026-09-30T20:15:00+08:00"
        }
      ]}
    />
  );
  expect(screen.getByText("暂停计划")).toBeInTheDocument();
  expect(screen.getByText("验证中")).toBeInTheDocument();
});