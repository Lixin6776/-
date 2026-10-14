import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

const getCdpConnection = vi.fn();
const getApiConnectionStatus = vi.fn();
const getLocalConfig = vi.fn();
const saveLocalConfig = vi.fn();

vi.mock("../lib/api", () => ({
  getCdpConnection: (...a: unknown[]) => getCdpConnection(...a),
  getApiConnectionStatus: (...a: unknown[]) => getApiConnectionStatus(...a),
  getLocalConfig: (...a: unknown[]) => getLocalConfig(...a),
  saveLocalConfig: (...a: unknown[]) => saveLocalConfig(...a),
  connectCdp: vi.fn(),
  resumeLiveWatch: vi.fn()
}));

import { DataSourcePanel } from "../components/DataSourcePanel";

test("数据源窗口同时展示 CDP 和 API 两条链路，并标出当前生效", async () => {
  getCdpConnection.mockResolvedValue({
    endpoint: "http://127.0.0.1:9222",
    connected: true,
    browser: "Chrome/155",
    pages: 4,
    qianchuan_pages: 4,
    error: null
  });
  getApiConnectionStatus.mockResolvedValue({
    configured: false,
    provider_preference: "cdp",
    base_url: "https://api.oceanengine.com",
    advertiser_id: 0
  });
  getLocalConfig.mockResolvedValue({
    saved: { room_name: "质润官方旗舰店" },
    effective: { room_name: "质润官方旗舰店", aavid: "1873104018827399" }
  });

  render(<DataSourcePanel />);

  await waitFor(() => expect(getCdpConnection).toHaveBeenCalled());
  // 两条链路都在
  expect(await screen.findByText("CDP 连接（读页面）")).toBeInTheDocument();
  expect(screen.getByText("API 连接（开放平台）")).toBeInTheDocument();
  // CDP 已连接、页面数正确
  expect(screen.getByText("已连接")).toBeInTheDocument();
  expect(screen.getByText(/千川页面 4 个/)).toBeInTheDocument();
  // API 未配置要说清楚
  expect(screen.getByText("未配置")).toBeInTheDocument();
  expect(screen.getByText(/需要先在巨量引擎开放平台申请应用/)).toBeInTheDocument();
  // 当前生效链路
  expect(screen.getByText("CDP（本机浏览器）")).toBeInTheDocument();
});

test("数据源窗口可以直接改直播间/账户（不用碰 .env）", async () => {
  getCdpConnection.mockResolvedValue({ connected: true, pages: 1, qianchuan_pages: 1, error: null, endpoint: "x", browser: "" });
  getApiConnectionStatus.mockResolvedValue({ configured: false, provider_preference: "cdp" });
  getLocalConfig.mockResolvedValue({
    saved: {},
    effective: { room_name: "质润官方旗舰店", aavid: "1873104018827399" }
  });

  render(<DataSourcePanel />);

  // 两个输入框 + 保存按钮
  expect(await screen.findByLabelText("直播间名称")).toBeInTheDocument();
  expect(screen.getByLabelText("账户 ID")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存" })).toBeInTheDocument();
  // 说明要讲清楚"留空=用 .env 的值"
  expect(screen.getByText(/留空 = 用 .env 里的值/)).toBeInTheDocument();
});
