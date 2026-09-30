import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { ActionParameterForm } from "../components/ActionParameterForm";


test("copy plan form requires a destination name", () => {
  render(<ActionParameterForm actionName="copy_plan" onSubmit={() => undefined} />);
  expect(screen.getByLabelText("目标计划名称")).toBeRequired();
});

test("copy plan form submits the destination name", async () => {
  const onSubmit = vi.fn();
  render(<ActionParameterForm actionName="copy_plan" onSubmit={onSubmit} />);
  fireEvent.change(screen.getByLabelText("目标计划名称"), { target: { value: "计划 B" } });
  fireEvent.click(screen.getByRole("button", { name: "生成预览" }));
  expect(onSubmit).toHaveBeenCalledWith({ name: "计划 B" });
});
