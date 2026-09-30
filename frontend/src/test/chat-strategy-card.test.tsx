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

  render(<ChatPanel onSend={onSend} />);
  fireEvent.change(screen.getByLabelText("输入投放问题"), { target: { value: "查看策略卡" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));

  expect(await screen.findByText("全域投放策略卡｜2026-09-30 22:54")).toBeInTheDocument();
  expect(screen.getByText("计划：计划 1876023119718580")).toBeInTheDocument();
  expect(screen.getByText("计划预算：¥9,999,999.00")).toBeInTheDocument();
  expect(screen.queryByText(/###/)).not.toBeInTheDocument();
});
