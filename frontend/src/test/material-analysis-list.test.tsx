import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { MaterialAnalysisList } from "../components/MaterialAnalysisList";


test("material analysis list shows direction and supports manual generation", () => {
  const onGenerate = vi.fn();
  render(
    <MaterialAnalysisList
      analyses={[
        {
          id: "m1",
          date: "2026-10-01",
          created_at: "2026-10-01T08:00:00+08:00",
          report_markdown: "## 素材分析报告｜2026-10-01\n\n### 三、新素材制作方向\n\n- 强化痛点表达"
        }
      ]}
      onGenerate={onGenerate}
    />
  );

  expect(screen.getByText(/2026-10-01 素材分析/)).toBeInTheDocument();
  expect(screen.getByText(/新素材制作方向/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "立即生成素材分析" }));
  expect(onGenerate).toHaveBeenCalledTimes(1);
});
