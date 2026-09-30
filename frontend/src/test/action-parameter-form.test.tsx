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
  fireEvent.change(screen.getByLabelText("计划 ID"), { target: { value: "plan-1" } });
  fireEvent.change(screen.getByLabelText("目标计划名称"), { target: { value: "计划 B" } });
  fireEvent.click(screen.getByRole("button", { name: "生成预览" }));
  expect(onSubmit).toHaveBeenCalledWith({ target_id: "plan-1", name: "计划 B" });
});

test("targeting form parses JSON before submission", () => {
  const onSubmit = vi.fn();
  render(<ActionParameterForm actionName="update_targeting" onSubmit={onSubmit} />);
  fireEvent.change(screen.getByLabelText("计划 ID"), { target: { value: "plan-1" } });
  fireEvent.change(screen.getByLabelText("定向 JSON"), { target: { value: '{"gender":"female"}' } });
  fireEvent.click(screen.getByRole("button", { name: "生成预览" }));
  expect(onSubmit).toHaveBeenCalledWith({
    target_id: "plan-1",
    targeting: { gender: "female" }
  });
});
