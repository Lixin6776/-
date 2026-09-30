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
