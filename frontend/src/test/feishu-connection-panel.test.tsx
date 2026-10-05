import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { FeishuConnectionPanel } from "../components/FeishuConnectionPanel";


const idleStatus = {
  configured: false,
  enabled: false,
  connection_mode: "webhook",
  webhook_masked: "",
  secret_configured: false,
  chat_id: "",
  chat_name: "",
  chat_share_link: "",
  auth_status: "idle",
  auth_message: "",
  auth_user_name: "",
  auto_send_live_review: true,
  auto_send_material_analysis: true,
  last_sent_at: "",
  last_error: ""
};


test("feishu panel starts QR login and displays the QR code", async () => {
  const load = vi.fn().mockResolvedValue(idleStatus);
  const start = vi.fn().mockResolvedValue({
    ...idleStatus,
    status: "pending",
    message: "请使用飞书扫码并完成授权。",
    verification_url: "https://accounts.feishu.cn/oauth/v1/device/verify",
    qr_data_url: "data:image/png;base64,ZmFrZQ=="
  });

  render(<FeishuConnectionPanel load={load} start={start} poll={load} />);

  expect(await screen.findByText("尚未连接飞书")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "开始扫码连接" }));

  expect(await screen.findByAltText("飞书扫码连接")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "打开飞书授权链接" })).toBeInTheDocument();
});


test("connected feishu group saves toggles and sends a test card", async () => {
  const connected = {
    ...idleStatus,
    configured: true,
    enabled: true,
    connection_mode: "qr",
    chat_id: "oc_qianchuan",
    chat_name: "千川 AI 投放助手",
    chat_share_link: "https://applink.feishu.cn/client/chat/open?openChatId=oc_qianchuan",
    auth_status: "connected"
  };
  const load = vi.fn().mockResolvedValue(connected);
  const save = vi.fn().mockResolvedValue(connected);
  const test = vi.fn().mockResolvedValue({ ok: true, message: "飞书测试卡片已发送" });

  render(<FeishuConnectionPanel load={load} save={save} test={test} />);

  expect(await screen.findByText(/已连接飞书助手群/)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("素材日报自动发送"));
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));

  await waitFor(() =>
    expect(save).toHaveBeenCalledWith({
      webhook_url: "",
      secret: "",
      enabled: true,
      auto_send_live_review: true,
      auto_send_material_analysis: false
    })
  );

  fireEvent.click(screen.getByRole("button", { name: "发送测试卡片" }));
  expect(await screen.findByText("飞书测试卡片已发送")).toBeInTheDocument();
});
