import { useEffect, useState } from "react";

import { ActionParameterForm } from "./components/ActionParameterForm";
import { ApiConnectionPanel } from "./components/ApiConnectionPanel";
import { ChatPanel, type ActionPreview, type ChatReply } from "./components/ChatPanel";
import { LearningCaseList } from "./components/LearningCaseList";
import { StrategyEvaluationPanel } from "./components/StrategyEvaluationPanel";
import { StrategySuggestionCard } from "./components/StrategySuggestionCard";
import { ConfirmationDialog } from "./components/ConfirmationDialog";
import { DecisionPanel } from "./components/DecisionPanel";
import { ExecutionTimeline } from "./components/ExecutionTimeline";
import { type LiveMonitorEvent } from "./components/LiveMonitorPanel";
import { LlmConnectionPanel } from "./components/LlmConnectionPanel";
import { PlanSnapshotPanel } from "./components/PlanSnapshotPanel";
import { StrategyBanner, type StrategyBannerProfile } from "./components/StrategyBanner";
import { InvestmentStrategyPanel } from "./components/InvestmentStrategyPanel";
import {
  connectMonitor,
  createActionConfirmation,
  executeActionConfirmation,
  getActiveProfile,
  getExecutionJobs,
  getApiConnectionStatus,
  getLearningCases,
  getLearningEvaluations,
  getLearningSuggestions,
  decideLearningSuggestion,
  previewAction,
  sendChat
} from "./lib/api";

const fallbackProfile: StrategyBannerProfile = {
  version: 0,
  business_direction: "未加载",
  primary_objective: "等待本地服务返回投放策略",
  hard_constraints: {},
  data_time: new Date().toISOString(),
  freshness: "stale"
};

type ExecutionJob = {
  id: string;
  action_name: string;
  status: string;
  created_at: string;
};

type ToolWindow = "strategy" | "decisions" | "jobs" | "llm" | "api" | "learning" | "evaluation" | "suggestions" | "advanced";

const tools: Array<{ id: ToolWindow; label: string }> = [
  { id: "strategy", label: "投放策略" },
  { id: "decisions", label: "决策" },
  { id: "jobs", label: "执行记录" },
  { id: "llm", label: "大模型" },
  { id: "api", label: "API 连接" },
  { id: "learning", label: "学习记录" },
  { id: "evaluation", label: "策略评估" },
  { id: "suggestions", label: "策略建议" },
  { id: "advanced", label: "高级操作" }
];

export default function App() {
  const [profile, setProfile] = useState<StrategyBannerProfile>(fallbackProfile);
  const [selectedPreview, setSelectedPreview] = useState<ActionPreview | null>(null);
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [learningCases, setLearningCases] = useState<any[]>([]);
  const [evaluations, setEvaluations] = useState<any[]>([]);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [apiStatus, setApiStatus] = useState({ configured: false, provider_preference: "cdp" as "api" | "cdp" });
  const [monitorEvent, setMonitorEvent] = useState<LiveMonitorEvent | null>(null);
  const [activeWindow, setActiveWindow] = useState<ToolWindow | null>(null);

  useEffect(() => {
    getActiveProfile()
      .then((value) => setProfile(value as StrategyBannerProfile))
      .catch(() => setProfile(fallbackProfile));
    getExecutionJobs().then((value) => setJobs(value as ExecutionJob[])).catch(() => undefined);
    getLearningCases().then(setLearningCases).catch(() => undefined);
    getLearningEvaluations().then(setEvaluations).catch(() => undefined);
    getLearningSuggestions().then(setSuggestions).catch(() => undefined);
    getApiConnectionStatus().then(setApiStatus).catch(() => undefined);
    return connectMonitor((event) => setMonitorEvent(event as LiveMonitorEvent));
  }, []);

  async function handleSend(message: string): Promise<ChatReply> {
    const result = await sendChat(message);
    return {
      message: result.message as string,
      preview: result.preview as ActionPreview | undefined
    };
  }

  async function handleAdvancedAction(actionName: string, params: Record<string, unknown>) {
    const targetId = String(params.target_id);
    const actionParams = Object.fromEntries(
      Object.entries(params).filter(([key]) => key !== "target_id")
    );
    const preview = await previewAction({
      action_name: actionName,
      target_id: targetId,
      params: actionParams
    });
    setSelectedPreview(preview as ActionPreview);
    setActiveWindow(null);
  }

  async function decideSuggestion(id: string, decision: "accept" | "reject") {
    const updated = await decideLearningSuggestion(id, decision);
    setSuggestions((current) =>
      current.map((item) => (item.id === id ? updated : item))
    );
  }

  async function confirmAction(preview: ActionPreview) {
    const confirmation = await createActionConfirmation({
      action_name: preview.action_name,
      target_id: preview.target_id,
      params: preview.normalized_params
    });
    const job = await executeActionConfirmation(confirmation.id);
    setJobs((current) => [job as ExecutionJob, ...current]);
    setSelectedPreview(null);
  }

  function renderWindow() {
    if (activeWindow === "strategy") {
      return (
        <InvestmentStrategyPanel
          onCreated={(value) => {
            setProfile({
              ...(value as StrategyBannerProfile),
              data_time: new Date().toISOString(),
              freshness: "fresh"
            });
            setActiveWindow(null);
          }}
        />
      );
    }
    if (activeWindow === "decisions") {
      return <DecisionPanel decisions={[]} onConfirm={() => undefined} onReject={() => undefined} />;
    }
    if (activeWindow === "jobs") return <ExecutionTimeline jobs={jobs} />;
    if (activeWindow === "llm") return <LlmConnectionPanel />;
    if (activeWindow === "api") {
      return (
        <ApiConnectionPanel
          configured={apiStatus.configured}
          providerPreference={apiStatus.provider_preference}
        />
      );
    }
    if (activeWindow === "learning") return <LearningCaseList cases={learningCases} />;
    if (activeWindow === "evaluation") {
      return evaluations[0] ? (
        <StrategyEvaluationPanel evaluation={evaluations[0]} />
      ) : (
        <p className="empty-state">暂无策略评估。</p>
      );
    }
    if (activeWindow === "suggestions") {
      return suggestions.length ? (
        <div className="window-stack">
          {suggestions.map((item) => (
            <StrategySuggestionCard
              key={item.id}
              suggestion={item}
              onAccept={(id) => decideSuggestion(id, "accept")}
              onReject={(id) => decideSuggestion(id, "reject")}
            />
          ))}
        </div>
      ) : (
        <p className="empty-state">暂无策略建议。</p>
      );
    }
    if (activeWindow === "advanced") {
      return (
        <ActionParameterForm
          actionName="copy_plan"
          onSubmit={(params) => handleAdvancedAction("copy_plan", params)}
        />
      );
    }
    return null;
  }

  const activeLabel = tools.find((item) => item.id === activeWindow)?.label;

  return (
    <div className="app-shell">
      <StrategyBanner profile={profile} />
      <PlanSnapshotPanel event={monitorEvent} />
      <div className="workspace byte-workspace">
        <nav className="tool-nav panel" aria-label="功能导航">
          {tools.map((item) => (
            <button
              className={activeWindow === item.id ? "tool-nav-item active" : "tool-nav-item"}
              key={item.id}
              type="button"
              onClick={() => setActiveWindow(item.id)}
            >
              <span>{item.label}</span>
              {item.id === "suggestions" && suggestions.length ? (
                <em>{suggestions.length}</em>
              ) : null}
            </button>
          ))}
        </nav>
        <main className="chat-main">
          <ChatPanel onSend={handleSend} onOpenConfirmation={setSelectedPreview} />
        </main>
      </div>
      {activeWindow ? (
        <div className="tool-window-backdrop" role="presentation" onClick={() => setActiveWindow(null)}>
          <section
            className="tool-window"
            role="dialog"
            aria-modal="true"
            aria-label={activeLabel}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="tool-window-header">
              <h2>{activeLabel}</h2>
              <button className="button-outline" type="button" onClick={() => setActiveWindow(null)}>
                关闭
              </button>
            </header>
            <div className="tool-window-body">{renderWindow()}</div>
          </section>
        </div>
      ) : null}
      {selectedPreview ? (
        <ConfirmationDialog
          preview={{ ...selectedPreview, constraints: profile.hard_constraints }}
          onConfirm={confirmAction}
          onCancel={() => setSelectedPreview(null)}
        />
      ) : null}
    </div>
  );
}
