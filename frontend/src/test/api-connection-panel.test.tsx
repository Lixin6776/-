import { render, screen } from "@testing-library/react";

import { ApiConnectionPanel } from "../components/ApiConnectionPanel";


test("API panel explains that secrets remain local", () => {
  render(<ApiConnectionPanel configured={false} providerPreference="cdp" />);
  expect(screen.getByText(/仅保存在本地/)).toBeInTheDocument();
  expect(screen.getByText(/CDP 回退/)).toBeInTheDocument();
});

test("API panel shows API-first routing when configured", () => {
  render(<ApiConnectionPanel configured={true} providerPreference="api" />);
  expect(screen.getByText(/投放操作默认优先走 API/)).toBeInTheDocument();
});
