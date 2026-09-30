import { useEffect, useState } from "react";

import { ChatPanel } from "./components/ChatPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { LiveMonitorPanel } from "./components/LiveMonitorPanel";
import { StrategyBanner, type StrategyBannerProfile } from "./components/StrategyBanner";
import { connectMonitor, getActiveProfile, sendChat } from "./lib/api";

const fallbackProfile: StrategyBannerProfile = {
  version: 0,
  business_direction: "未加载",
  primary_objective: "等待本地服务返回策略画像",
  hard_constraints: {},
  data_time: new Date().toISOString(),
  freshness: "stale"
};

export default function App() {
  const [profile, setProfile] = useState<StrategyBannerProfile>(fallbackProfile);

  useEffect(() => {
    getActiveProfile()
      .then((value) => setProfile(value as StrategyBannerProfile))
      .catch(() => setProfile(fallbackProfile));
    return connectMonitor(() => undefined);
  }, []);

  async function handleSend(message: string) {
    const result = await sendChat(message);
    return result.message as string;
  }

  return (
    <div className="app-shell">
      <StrategyBanner profile={profile} />
      <main className="workspace">
        <ChatPanel onSend={handleSend} />
        <aside className="context-column">
          <LiveMonitorPanel />
          <DecisionPanel decisions={[]} onConfirm={() => undefined} onReject={() => undefined} />
        </aside>
      </main>
    </div>
  );
}