import { ChatPanel } from "./components/ChatPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { LiveMonitorPanel } from "./components/LiveMonitorPanel";
import { StrategyBanner } from "./components/StrategyBanner";

const demoProfile = {
  version: 1,
  business_direction: "稳定放量",
  primary_objective: "在 ROI >= 2.5 的前提下提升成交额",
  hard_constraints: { daily_budget_max: 5000 },
  data_time: "2026-09-30T20:15:00+08:00",
  freshness: "fresh" as const
};

export default function App() {
  return (
    <div className="app-shell">
      <StrategyBanner profile={demoProfile} />
      <main className="workspace">
        <ChatPanel />
        <aside className="context-column">
          <LiveMonitorPanel />
          <DecisionPanel decisions={[]} onConfirm={() => undefined} onReject={() => undefined} />
        </aside>
      </main>
    </div>
  );
}