import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { LlmConnectionPanel } from "../components/LlmConnectionPanel";


test("DeepSeek panel saves local configuration and tests connection", async () => {
  const load = vi.fn().mockResolvedValue({
    configured: true,
    base_url: "https://api.deepseek.com",
    model: "deepseek-chat",
    api_key_configured: true
  });
  const save = vi.fn().mockResolvedValue({
    configured: true,
    base_url: "https://api.deepseek.com",
    model: "deepseek-reasoner",
    api_key_configured: true
  });
  const test = vi.fn().mockResolvedValue({ ok: true, message: "大模型连接成功" });

  const { container } = render(<LlmConnectionPanel load={load} save={save} test={test} />);

  expect(
    container.querySelector('select option[value="deepseek-v4-flash"]')
  ).not.toBeNull();

  expect(await screen.findByText(/已配置：deepseek-chat/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("DeepSeek 模型"), {
    target: { value: "deepseek-reasoner" }
  });
  fireEvent.change(screen.getByLabelText("DeepSeek API Key"), {
    target: { value: "secret-key" }
  });
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));

  await waitFor(() =>
    expect(save).toHaveBeenCalledWith({
      base_url: "https://api.deepseek.com",
      model: "deepseek-reasoner",
      api_key: "secret-key"
    })
  );
  expect(screen.queryByDisplayValue("secret-key")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(await screen.findByText("大模型连接成功")).toBeInTheDocument();
});
