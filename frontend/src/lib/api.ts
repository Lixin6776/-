const API_BASE = "http://127.0.0.1:8000";

export async function getActiveProfile() {
  const response = await fetch(`${API_BASE}/api/profiles/active`);
  if (!response.ok) throw new Error("Failed to load strategy profile");
  return response.json();
}

export async function sendChat(message: string) {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });
  if (!response.ok) throw new Error("Chat request failed");
  return response.json();
}

export function connectMonitor(onEvent: (event: unknown) => void) {
  const source = new EventSource(`${API_BASE}/api/monitor/events`);
  source.addEventListener("monitor", (event) => onEvent(JSON.parse(event.data)));
  return () => source.close();
}
export async function createActionConfirmation(action: {
  action_name: string;
  target_id: string;
  params: Record<string, unknown>;
}) {
  const response = await fetch(`${API_BASE}/api/actions/confirmations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action })
  });
  if (!response.ok) throw new Error("Confirmation creation failed");
  return response.json();
}

export async function executeActionConfirmation(confirmationId: string) {
  const response = await fetch(
    `${API_BASE}/api/actions/confirmations/${confirmationId}/execute`,
    { method: "POST" }
  );
  if (!response.ok) throw new Error("Action execution failed");
  return response.json();
}

export async function getExecutionJobs() {
  const response = await fetch(`${API_BASE}/api/actions/jobs`);
  if (!response.ok) throw new Error("Failed to load execution jobs");
  return response.json();
}
export async function previewAction(action: {
  action_name: string;
  target_id: string;
  params: Record<string, unknown>;
}) {
  const response = await fetch(`${API_BASE}/api/actions/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action })
  });
  if (!response.ok) throw new Error("Action preview failed");
  return response.json();
}
export async function getLearningCases() {
  const response = await fetch(`${API_BASE}/api/learning/cases`);
  if (!response.ok) throw new Error("Failed to load learning cases");
  return response.json();
}

export async function getLearningEvaluations() {
  const response = await fetch(`${API_BASE}/api/learning/evaluations`);
  if (!response.ok) throw new Error("Failed to load evaluations");
  return response.json();
}

export async function getLearningSuggestions() {
  const response = await fetch(`${API_BASE}/api/learning/suggestions`);
  if (!response.ok) throw new Error("Failed to load suggestions");
  return response.json();
}

export async function decideLearningSuggestion(id: string, decision: "accept" | "reject", reason = "") {
  const response = await fetch(`${API_BASE}/api/learning/suggestions/${id}/${decision}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason })
  });
  if (!response.ok) throw new Error("Suggestion decision failed");
  return response.json();
}
export async function getApiConnectionStatus() {
  const response = await fetch(`${API_BASE}/api/api-connection/status`);
  if (!response.ok) throw new Error("Failed to load API connection status");
  return response.json();
}

export async function getCurrentPlanSnapshot() {
  const response = await fetch(`${API_BASE}/api/plans/current`);
  if (!response.ok) throw new Error("Failed to load current plan snapshot");
  return response.json();
}

export async function getLlmConnectionStatus() {
  const response = await fetch(`${API_BASE}/api/llm-connection/status`);
  if (!response.ok) throw new Error("Failed to load LLM connection status");
  return response.json();
}

export async function saveLlmConnection(config: {
  base_url: string;
  model: string;
  api_key: string;
}) {
  const response = await fetch(`${API_BASE}/api/llm-connection/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config)
  });
  if (!response.ok) throw new Error("Failed to save LLM connection");
  return response.json();
}

export async function testLlmConnection() {
  const response = await fetch(`${API_BASE}/api/llm-connection/test`, {
    method: "POST"
  });
  if (!response.ok) throw new Error("LLM connection test failed");
  return response.json();
}

export async function createStrategyProfile(profile: {
  name: string;
  business_direction: string;
  primary_objective: string;
  secondary_objectives?: string[];
  hard_constraints?: Record<string, unknown>;
  monitoring_config?: Record<string, unknown>;
  allowed_actions?: string[];
  notification_policy?: Record<string, unknown>;
}) {
  const response = await fetch(`${API_BASE}/api/profiles/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile)
  });
  if (!response.ok) throw new Error("Failed to create strategy profile");
  return response.json();
}

export async function getLiveReviews() {
  const response = await fetch(`${API_BASE}/api/reviews`);
  if (!response.ok) throw new Error("Failed to load live reviews");
  return response.json();
}

export async function getLatestLiveReview() {
  const response = await fetch(`${API_BASE}/api/reviews/latest`);
  if (!response.ok) throw new Error("Failed to load latest live review");
  return response.json();
}
export async function getMaterialAnalyses() {
  const response = await fetch(`${API_BASE}/api/material-analyses`);
  if (!response.ok) throw new Error("Failed to load material analyses");
  return response.json();
}

export async function generateMaterialAnalysis() {
  const response = await fetch(`${API_BASE}/api/material-analyses/generate`, {
    method: "POST"
  });
  if (!response.ok) throw new Error("Material analysis generation failed");
  return response.json();
}

export function connectNotifications(onEvent: (event: unknown) => void) {
  const source = new EventSource(`${API_BASE}/api/notifications/events`);
  source.addEventListener("notification", (event) => onEvent(JSON.parse(event.data)));
  return () => source.close();
}
