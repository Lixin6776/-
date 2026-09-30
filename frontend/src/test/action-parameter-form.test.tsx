import { render, screen } from "@testing-library/react";

import { ActionParameterForm } from "../components/ActionParameterForm";


test("copy plan form requires a destination name", () => {
  render(<ActionParameterForm actionName="copy_plan" onSubmit={() => undefined} />);
  expect(screen.getByLabelText("目标计划名称")).toBeRequired();
});