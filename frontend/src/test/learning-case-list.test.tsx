import { render, screen } from "@testing-library/react";

import { LearningCaseList } from "../components/LearningCaseList";


test("learning case list shows action and evidence status", () => {
  render(
    <LearningCaseList
      cases={[
        {
          id: "case-1",
          action_name: "pause_plan",
          status: "observed",
          strategy_profile_version: 3,
          context: { roi: 2.4 }
        }
      ]}
    />
  );
  expect(screen.getByText("暂停计划")).toBeInTheDocument();
  expect(screen.getByText("策略 v3")).toBeInTheDocument();
});