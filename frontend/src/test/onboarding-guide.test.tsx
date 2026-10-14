import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

const getLocalConfig = vi.fn();
const getCdpConnection = vi.fn();
const getLlmConnectionStatus = vi.fn();
const getLiveWatchLogs = vi.fn();

vi.mock("../lib/api", () => ({
  getLocalConfig: (...a: unknown[]) => getLocalConfig(...a),
  getCdpConnection: (...a: unknown[]) => getCdpConnection(...a),
  getLlmConnectionStatus: (...a: unknown[]) => getLlmConnectionStatus(...a),
  getLiveWatchLogs: (...a: unknown[]) => getLiveWatchLogs(...a),
  connectCdp: vi.fn()
}));

import { OnboardingGuide } from "../components/OnboardingGuide";

function mockAll(overrides: Partial<Record<string, unknown>> = {}) {
  getLocalConfig.mockResolvedValue(
    overrides.localConfig ?? { saved: {}, effective: { room_name: "", aavid: "" } }
  );
  getCdpConnection.mockResolvedValue(
    overrides.cdp ?? { connected: false, pages: 0, qianchuan_pages: 0, error: null }
  );
  getLlmConnectionStatus.mockResolvedValue(
    overrides.llm ?? { configured: false }
  );
  getLiveWatchLogs.mockResolvedValue(overrides.logs ?? []);
}

test("没配好时显示新手上路清单，并指出当前卡在哪一步", async () => {
  mockAll();
  window.localStorage.removeItem("qca_onboarding_hidden");
  render(<OnboardingGuide />);

  await waitFor(() => expect(getLocalConfig).toHaveBeenCalled());
  expect(await screen.findByText(/新手上路（0\/4）/)).toBeInTheDocument();
  expect(screen.getByText(/填写直播间名称/)).toBeInTheDocument();
  expect(screen.getByText("连接数据源（本机 Chrome）")).toBeInTheDocument();
  expect(screen.getByText(/填大模型 Key/)).toBeInTheDocument();
  expect(screen.getByText(/跑出第一份盯盘报表/)).toBeInTheDocument();
});

test("全部都配好了就不再显示引导", async () => {
  mockAll({
    localConfig: { saved: { room_name: "质润官方旗舰店" }, effective: { room_name: "质润官方旗舰店" } },
    cdp: { connected: true, pages: 3, qianchuan_pages: 3, error: null },
    llm: { configured: true },
    logs: [{ id: "r1" }]
  });
  window.localStorage.removeItem("qca_onboarding_hidden");
  render(<OnboardingGuide />);

  await waitFor(() => expect(getLiveWatchLogs).toHaveBeenCalled());
  expect(screen.queryByText(/新手上路/)).not.toBeInTheDocument();
});
