import { fireEvent, render, screen } from "@testing-library/react";

import { ChatPanel } from "../components/ChatPanel";


test("chat panel renders strategy card as structured content", async () => {
  const onSend = async () => ({
    message: [
      "### 全域投放策略卡｜2026-09-30 22:54",
      "",
      "**计划：计划 1876023119718580**",
      "",
      "- 账户：质润官方旗舰店",
      "- 计划预算：¥9,999,999.00",
      "- 目标ROI：2.60"
    ].join("\n")
  });

  const { container } = render(<ChatPanel onSend={onSend} />);
  fireEvent.change(screen.getByLabelText("输入投放问题"), { target: { value: "查看策略卡" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));

  expect(await screen.findByText("全域投放策略卡｜2026-09-30 22:54")).toBeInTheDocument();
  expect(screen.getByText("计划：计划 1876023119718580")).toBeInTheDocument();
  expect(screen.getByText("计划预算：¥9,999,999.00")).toBeInTheDocument();
  expect(screen.queryByText(/###/)).not.toBeInTheDocument();
  expect(container.querySelector(".message-user")).not.toBeNull();
  expect(container.querySelector(".message-assistant")).not.toBeNull();
});


test("chat panel unwraps json-formatted assistant messages", async () => {
  const onSend = async () => ({
    message: JSON.stringify({ kind: "analysis", message: "JSON 包装已恢复" })
  });

  render(<ChatPanel onSend={onSend} />);
  fireEvent.change(screen.getByLabelText("输入投放问题"), { target: { value: "总结一下" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));

  expect(await screen.findByText("JSON 包装已恢复")).toBeInTheDocument();
  expect(screen.queryByText(/"kind"/)).not.toBeInTheDocument();
});

test("chat panel recovers json messages with literal newlines", async () => {
  const onSend = async () => ({
    message: '{\n  "kind": "analysis",\n  "message": "第一行\n第二行"\n}'
  });

  render(<ChatPanel onSend={onSend} />);
  fireEvent.change(screen.getByLabelText("输入投放问题"), { target: { value: "总结一下" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));

  expect(await screen.findByText(/第一行/)).toBeInTheDocument();
  expect(screen.getByText(/第二行/)).toBeInTheDocument();
  expect(screen.queryByText(/"kind"/)).not.toBeInTheDocument();
});