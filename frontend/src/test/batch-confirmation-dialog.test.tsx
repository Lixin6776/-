import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { BatchConfirmationDialog } from "../components/BatchConfirmationDialog";


test("batch dialog blocks confirmation when any preview is blocked", () => {
  const onConfirm = vi.fn();
  render(
    <BatchConfirmationDialog
      previews={[
        { target_id: "plan-1", target_name: "计划 A", allowed: true, blockers: [] },
        { target_id: "plan-2", target_name: "计划 B", allowed: false, blockers: ["目标不存在"] }
      ]}
      onConfirm={onConfirm}
      onCancel={() => undefined}
    />
  );
  fireEvent.click(screen.getByLabelText("我了解批量操作影响"));
  expect(screen.getByRole("button", { name: "确认执行批量操作" })).toBeDisabled();
  expect(onConfirm).not.toHaveBeenCalled();
});