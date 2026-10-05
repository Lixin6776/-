import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { FeishuConnectionPanel } from "../components/FeishuConnectionPanel";


test("feishu panel saves config and sends a test card", async () => {
  const load = vi.fn().mockResolvedValue({
    configured: true,
    enabled: true,
    webhook_masked: "https://open.feishu.cn/.../hook/****",
    secret_configured: true,
    auto_send_live_review: true,
    auto_send_material_analysis: false,
    last_sent_at: "",
    last_error: ""
  });
  const save = vi.fn().mockResolvedValue({
    configured: true,
    enabled: true,
    webhook_masked: "https://open.feishu.cn/.../hook/****",
    secret_configured: true,
    auto_send_live_review: true,
    auto_send_material_analysis: true,
    last_sent_at: "",
    last_error: ""
  });
  const test = vi.fn().mockResolvedValue({ ok: true, message: "飞书测试卡片已发送" });

  render(<FeishuConnectionPanel load={load} save={save} test={test} />);

  expect(await screen.findByText(/飞书已连接/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("飞书 Webhook URL"), {
    target: { value: "https://open.feishu.cn/open-apis/bot/v2/hook/new" }
  });
  fireEvent.change(screen.getByLabelText("飞书签名密钥"), {
    target: { value: "new-secret" }
  });
  fireEvent.click(screen.getByLabelText("素材日报自动发送"));
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));

  await waitFor(() =>
    expect(save).toHaveBeenCalledWith({
      webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/new",
      secret: "new-secret",
      enabled: true,
      auto_send_live_review: true,
      auto_send_material_analysis: true
    })
  );

  fireEvent.click(screen.getByRole("button", { name: "发送测试卡片" }));
  expect(await screen.findByText("飞书测试卡片已发送")).toBeInTheDocument();
});
