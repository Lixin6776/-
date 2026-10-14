import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

const getActiveProfile = vi.fn();
const createStrategyProfile = vi.fn();

vi.mock("../lib/api", () => ({
  getActiveProfile: (...a: unknown[]) => getActiveProfile(...a),
  createStrategyProfile: (...a: unknown[]) => createStrategyProfile(...a)
}));

import { ThresholdPanel } from "../components/ThresholdPanel";

test("判断标准：读当前值、留空=自动、保存生成新版本", async () => {
  getActiveProfile.mockResolvedValue({
    version: 1,
    name: "质润官方旗舰店 · 全域直播投放",
    business_direction: "全域直播投放",
    primary_objective: "稳定放量",
    secondary_objectives: [],
    hard_constraints: { roi_target: 2.7, thresholds: { gpm: 2500 } },
    monitoring_config: { interval_minutes: 5 },
    allowed_actions: [],
    notification_policy: { dedupe_minutes: 10 }
  });
  createStrategyProfile.mockResolvedValue({
    version: 2,
    name: "质润官方旗舰店 · 全域直播投放",
    business_direction: "全域直播投放",
    primary_objective: "稳定放量",
    hard_constraints: { roi_target: 2.7, thresholds: { gpm: 2500, cpm: 120 } },
    allowed_actions: []
  });

  render(<ThresholdPanel />);

  await waitFor(() => expect(getActiveProfile).toHaveBeenCalled());
  // 读到了当前设定的值
  const gpm = (await screen.findByLabelText("GPM")) as HTMLInputElement;
  expect(gpm.value).toBe("2500");
  // 没设的留空
  expect((screen.getByLabelText("CPM") as HTMLInputElement).value).toBe("");
  // 说明文案要讲清楚"留空=自动"
  expect(screen.getByText(/留空则自动/)).toBeInTheDocument();
  // ROI 目标不在这里设，避免和计划打架
  expect(screen.getByText(/ROI 目标不在这里设/)).toBeInTheDocument();
});
