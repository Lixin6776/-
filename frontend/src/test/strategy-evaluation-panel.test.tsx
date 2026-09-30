import { render, screen } from "@testing-library/react";

import { StrategyEvaluationPanel } from "../components/StrategyEvaluationPanel";


test("evaluation panel shows sample size and confidence", () => {
  render(
    <StrategyEvaluationPanel
      evaluation={{
        sample_size: 24,
        confidence: "high",
        verdict: "beneficial",
        evidence: { mean_roi_delta: 0.4, counterexamples: 3 }
      }}
    />
  );
  expect(screen.getByText("样本量")).toBeInTheDocument();
  expect(screen.getByText("24")).toBeInTheDocument();
  expect(screen.getByText(/高置信度/)).toBeInTheDocument();
});