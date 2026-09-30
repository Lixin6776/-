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
import { LiveMonitorPanel, type LiveMonitorEvent } from "./components/LiveMonitorPanel";
import { StrategyBanner, type StrategyBannerProfile } from "./components/StrategyBanner";
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
  primary_objective: "等待本地服务返回策略画像",
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

export default function App() {
  const [profile, setProfile] = useState<StrategyBannerProfile>(fallbackProfile);
  const [selectedPreview, setSelectedPreview] = useState<ActionPreview | null>(null);
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [learningCases, setLearningCases] = useState<any[]>([]);
  const [evaluations, setEvaluations] = useState<any[]>([]);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [apiStatus, setApiStatus] = useState({ configured: false, provider_preference: "cdp" as "api" | "cdp" });
  const [monitorEvent, setMonitorEvent] = useState<LiveMonitorEvent | null>(null);

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

  return (
    <div className="app-shell">
      <StrategyBanner profile={profile} />
      <main className="workspace">
        <ChatPanel onSend={handleSend} onOpenConfirmation={setSelectedPreview} />
        <aside className="context-column">
          <LiveMonitorPanel event={monitorEvent} />
          <DecisionPanel decisions={[]} onConfirm={() => undefined} onReject={() => undefined} />
          <ExecutionTimeline jobs={jobs} />
          <ApiConnectionPanel
            configured={apiStatus.configured}
            providerPreference={apiStatus.provider_preference}
          />
          <LearningCaseList cases={learningCases} />
          {evaluations[0] ? <StrategyEvaluationPanel evaluation={evaluations[0]} /> : null}
          {suggestions.map((item) => (
            <StrategySuggestionCard
              key={item.id}
              suggestion={item}
              onAccept={(id) => decideSuggestion(id, "accept")}
              onReject={(id) => decideSuggestion(id, "reject")}
            />
          ))}
          <details className="panel advanced-actions">
            <summary>高级投放操作</summary>
            <ActionParameterForm actionName="copy_plan" onSubmit={(params) => handleAdvancedAction("copy_plan", params)} />
          </details>
        </aside>
      </main>
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