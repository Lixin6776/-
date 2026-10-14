import { render, screen } from "@testing-library/react";

import { ReportMessage } from "../components/ReportMessage";

const SAMPLE = `## 直播盯盘报表 · 10-06 12:56

> 计划 1876035797292211　|　目标 ROI 2.60　|　数据源 cdp

### 实时数据

| 指标 | 数值 |
| --- | ---: |
| 综合营销 ROI | 1.72 |
| 综合成本 | ¥18,084.55 |
| 实时在线人数 | 23 |

### 发现的问题

- **ROI 未达标** — 1.72 低于目标 2.60
- 消耗连续两个周期几乎不动

### 调整方案（需你确认）

1. 先看消耗集中在哪条计划。
2. 优先降追投占比。

### 操作日志

- 暂无已执行的账户操作

---

### 三、新素材制作方向

- 复刻高 ROI 素材的前 3 秒钩子。
`;

test("renders report markdown as structured HTML instead of raw text", () => {
  render(<ReportMessage content={SAMPLE} />);

  // 标题变成真正的标题，而不是字面的 ##
  expect(screen.getByText("直播盯盘报表 · 10-06 12:56")).toBeInTheDocument();
  expect(screen.getByText("实时数据")).toBeInTheDocument();
  expect(screen.getByText("三、新素材制作方向")).toBeInTheDocument();

  // 表格被渲染成 table
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.getByText("综合成本")).toBeInTheDocument();
  expect(screen.getByText("¥18,084.55")).toBeInTheDocument();

  // 加粗
  const bold = screen.getByText("ROI 未达标");
  expect(bold.tagName).toBe("STRONG");

  // 有序 / 无序列表
  expect(screen.getByText("先看消耗集中在哪条计划。")).toBeInTheDocument();
  expect(screen.getByText("消耗连续两个周期几乎不动")).toBeInTheDocument();

  // 不应残留 markdown 记号
  const text = document.body.textContent ?? "";
  expect(text).not.toContain("##");
  expect(text).not.toContain("| --- |");
  expect(text).not.toContain("**");
});

test("keeps every section of a long report", () => {
  const long = [
    "## 素材分析报告｜2026-10-05",
    "",
    "### 一、每日素材消耗概况",
    "",
    "- 素材总消耗：¥51,800.28",
    "",
    "### 二、新素材情况",
    "",
    "| 素材 | 消耗 |",
    "| --- | ---: |",
    "| 素材A | ¥345.76 |",
    "",
    "### 三、跑量素材较上一日变化",
    "",
    "- 增长素材：3 条",
    "",
    "### 四、素材产出方向",
    "",
    "1. 复刻素材A。",
    "",
    "### 五、执行提醒",
    "",
    "- 所有调整都需要人工确认。"
  ].join("\n");
  render(<ReportMessage content={long} />);
  const text = document.body.textContent ?? "";
  for (const marker of ["一、每日素材消耗概况", "二、新素材情况", "三、跑量素材较上一日变化", "四、素材产出方向", "五、执行提醒"]) {
    expect(text).toContain(marker);
  }
});
