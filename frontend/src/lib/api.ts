const API_BASE = "http://127.0.0.1:8000";

export async function getActiveProfile() {
  const response = await fetch(`${API_BASE}/api/profiles/active`);
  if (!response.ok) throw new Error("Failed to load strategy profile");
  return response.json();
}

export async function sendChat(message: string, images: string[] = []) {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, images })
  });
  if (!response.ok) throw new Error("Chat request failed");
  return response.json();
}

/**
 * 全局单例 SSE。
 *
 * 每次组件挂载都新建 EventSource 会把浏览器的同源连接占满（HTTP/1.1 每源 6 条），
 * 之后所有请求都会排队卡死。这里保证每个地址只保留一条长连接。
 */
const sseListeners = new Map<string, Set<(event: unknown) => void>>();
const sseSources = new Map<string, EventSource>();

function subscribeSse(
  path: string,
  eventName: string,
  onEvent: (event: unknown) => void
): () => void {
  let listeners = sseListeners.get(path);
  if (!listeners) {
    listeners = new Set();
    sseListeners.set(path, listeners);
  }
  listeners.add(onEvent);

  if (!sseSources.has(path)) {
    const source = new EventSource(`${API_BASE}${path}`);
    source.addEventListener(eventName, (event) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse((event as MessageEvent).data);
      } catch {
        return;
      }
      const current = sseListeners.get(path);
      if (current) current.forEach((fn) => fn(parsed));
    });
    sseSources.set(path, source);
  }

  return () => {
    const current = sseListeners.get(path);
    if (!current) return;
    current.delete(onEvent);
    // 注意：故意不关闭 source，保持全局唯一的一条长连接
  };
}

export function connectMonitor(onEvent: (event: unknown) => void) {
  return subscribeSse("/api/monitor/events", "monitor", onEvent);
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
  return subscribeSse("/api/notifications/events", "notification", onEvent);
}


export async function getFeishuStatus() {
  const response = await fetch(`${API_BASE}/api/feishu/status`);
  if (!response.ok) throw new Error("Failed to load Feishu status");
  return response.json();
}

export async function saveFeishuConfig(config: {
  webhook_url: string;
  secret: string;
  enabled: boolean;
  auto_send_live_review: boolean;
  auto_send_material_analysis: boolean;
}) {
  const response = await fetch(`${API_BASE}/api/feishu/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config)
  });
  if (!response.ok) throw new Error("Failed to save Feishu config");
  return response.json();
}

export async function testFeishuConnection() {
  const response = await fetch(`${API_BASE}/api/feishu/test`, {
    method: "POST"
  });
  if (!response.ok) throw new Error("Feishu connection test failed");
  return response.json();
}


export async function startFeishuLogin() {
  const response = await fetch(`${API_BASE}/api/feishu/login/start`, {
    method: "POST"
  });
  if (!response.ok) throw new Error("Failed to start Feishu login");
  return response.json();
}

export async function getFeishuLoginStatus() {
  const response = await fetch(`${API_BASE}/api/feishu/login/status`);
  if (!response.ok) throw new Error("Failed to load Feishu login status");
  return response.json();
}

export type LiveWatchStatus = {
  running: boolean;
  /** 用户「想不想让它跑」。关窗口/关机不算停止，只有点停止才变 false */
  desired_running?: boolean;
  /** 想跑但没在跑 = 断开，需要点「恢复盯盘」 */
  interrupted?: boolean;
  /** 离上一次成功读取过去了多少秒 */
  gap_seconds?: number | null;
  last_tick_at?: string;
  last_report_at?: string;
  room_name?: string | null;
  live_started_at?: string | null;
  last_error?: string;
  consecutive_failures?: number;
  interval_seconds: number;
  tick_count: number;
  last_run: string;
  reports: number;
  latest?: LiveWatchReport | null;
  resumed?: boolean;
  resume_note?: string;
};

export type CdpConnectionStatus = {
  endpoint: string;
  connected: boolean;
  browser: string | null;
  pages: number;
  qianchuan_pages: number;
  error: string | null;
  launched?: boolean;
  chrome_found?: boolean;
  profile?: string | null;
  profile_kind?: string | null;
  needs_login?: boolean;
  needs_chrome_restart?: boolean;
  mode_used?: string;
  message?: string;
};

export type LiveWatchReport = {
  id: string;
  created_at: string;
  level: string;
  source: string;
  roi: number | null;
  spend: number;
  gmv: number;
  gpm: number | null;
  online_viewers: number;
  orders: number;
  spend_delta: number | null;
  roi_target: number | null;
  problems: string[];
  adjustments: string[];
  operations: Array<{
    job_id: string;
    action_name: string;
    status: string;
    created_at: string;
  }>;
  report_markdown: string;
};

export async function getLiveWatchStatus(): Promise<LiveWatchStatus> {
  const response = await fetch(`${API_BASE}/api/live-watch/status`);
  if (!response.ok) throw new Error("Failed to load live watch status");
  return response.json();
}

export async function startLiveWatch(): Promise<LiveWatchStatus> {
  const response = await fetch(`${API_BASE}/api/live-watch/start`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to start live watch");
  return response.json();
}

export async function resumeLiveWatch(): Promise<LiveWatchStatus> {
  const response = await fetch(`${API_BASE}/api/live-watch/resume`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to resume live watch");
  return response.json();
}

export async function getCdpConnection(): Promise<CdpConnectionStatus> {
  const response = await fetch(`${API_BASE}/api/live-watch/connection`);
  if (!response.ok) throw new Error("Failed to load data source status");
  return response.json();
}

export async function connectCdp(
  mode: "auto" | "default" | "assistant" = "auto"
): Promise<CdpConnectionStatus> {
  const response = await fetch(
    `${API_BASE}/api/live-watch/connection/connect?mode=${mode}`,
    { method: "POST" }
  );
  if (!response.ok) throw new Error("Failed to connect data source");
  return response.json();
}

export async function heartbeatLiveWatch(): Promise<LiveWatchStatus> {
  const response = await fetch(`${API_BASE}/api/live-watch/heartbeat`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to heartbeat live watch");
  return response.json();
}

export async function stopLiveWatch(): Promise<LiveWatchStatus> {
  const response = await fetch(`${API_BASE}/api/live-watch/stop`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to stop live watch");
  return response.json();
}

export async function tickLiveWatch(): Promise<LiveWatchReport> {
  const response = await fetch(`${API_BASE}/api/live-watch/tick`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to run live watch tick");
  return response.json();
}

export async function getLiveWatchLogs(limit = 30): Promise<LiveWatchReport[]> {
  const response = await fetch(`${API_BASE}/api/live-watch/logs?limit=${limit}`);
  if (!response.ok) throw new Error("Failed to load live watch logs");
  return response.json();
}

// --- 直播运营助手（跨场次保留的运营对话）-----------------------------------

export type OpsChatMessage = {
  id: string;
  created_at: string;
  day?: string;
  role: "user" | "assistant";
  kind?: "briefing" | "review" | "chat";
  content: string;
  meta?: { images?: string[] };
};

/** 聊天里图片地址是后端相对路径，拼成可直接给 <img src> 用的完整地址。 */
export function opsChatImageUrl(path: string): string {
  return /^https?:/i.test(path) ? path : `${API_BASE}${path}`;
}

export async function getOpsChatMessages(limit = 100): Promise<OpsChatMessage[]> {
  const response = await fetch(`${API_BASE}/api/ops-chat/messages?limit=${limit}`);
  if (!response.ok) throw new Error("Failed to load ops chat");
  return response.json();
}

export async function sendOpsChat(
  message: string,
  images: string[] = []
): Promise<OpsChatMessage> {
  const response = await fetch(`${API_BASE}/api/ops-chat/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, images })
  });
  if (!response.ok) throw new Error("Failed to send ops chat message");
  return response.json();
}

export async function generateOpsBriefing(): Promise<OpsChatMessage> {
  const response = await fetch(`${API_BASE}/api/ops-chat/briefing`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to generate briefing");
  return response.json();
}

// --- 本机配置（直播间 / 账户）------------------------------------------------

export type LocalConfig = {
  saved: { room_name?: string; aavid?: string };
  effective: { room_name?: string; aavid?: string };
};

export async function getLocalConfig(): Promise<LocalConfig> {
  const response = await fetch(`${API_BASE}/api/local-config`);
  if (!response.ok) throw new Error("Failed to load local config");
  return response.json();
}

export async function saveLocalConfig(patch: {
  room_name?: string;
  aavid?: string;
}): Promise<{ saved: Record<string, string>; message: string }> {
  const response = await fetch(`${API_BASE}/api/local-config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch)
  });
  if (!response.ok) throw new Error("Failed to save local config");
  return response.json();
}
