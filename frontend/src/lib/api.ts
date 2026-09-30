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