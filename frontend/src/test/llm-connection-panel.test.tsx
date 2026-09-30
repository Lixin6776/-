import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { LlmConnectionPanel } from "../components/LlmConnectionPanel";


test("LLM panel saves local configuration and tests connection", async () => {
  const load = vi.fn().mockResolvedValue({
    configured: true,
    base_url: "https://llm.example/v1",
    model: "test-model",
    api_key_configured: true
  });
  const save = vi.fn().mockResolvedValue({
    configured: true,
    base_url: "https://llm.example/v2",
    model: "test-model-2",
    api_key_configured: true
  });
  const test = vi.fn().mockResolvedValue({ ok: true, message: "大模型连接成功" });

  render(<LlmConnectionPanel load={load} save={save} test={test} />);

  expect(await screen.findByText(/已配置：test-model/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("大模型 API 地址"), {
    target: { value: "https://llm.example/v2" }
  });
  fireEvent.change(screen.getByLabelText("大模型模型名称"), {
    target: { value: "test-model-2" }
  });
  fireEvent.change(screen.getByLabelText("大模型 API Key"), {
    target: { value: "secret-key" }
  });
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));

  await waitFor(() =>
    expect(save).toHaveBeenCalledWith({
      base_url: "https://llm.example/v2",
      model: "test-model-2",
      api_key: "secret-key"
    })
  );
  expect(screen.queryByDisplayValue("secret-key")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(await screen.findByText("大模型连接成功")).toBeInTheDocument();
});
