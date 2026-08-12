import { apiClient, authenticatedHeaders, getBackendBaseUrl, type createApiClient, ApiClientError } from "./client";
import type { AssistantHistory, AssistantMessage } from "@/types/assistant";

type ApiClient = ReturnType<typeof createApiClient>;
export function getAssistantMessages(runId: string, conversationId?: string, client: ApiClient = apiClient): Promise<AssistantHistory> {
  const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : "";
  return client.get<AssistantHistory>(`/api/v1/runs/${encodeURIComponent(runId)}/assistant/messages${query}`);
}
export function sendAssistantMessage(runId: string, request: { message: string; conversation_id?: string; idempotency_key?: string; request_id?: string; retry_of_message_id?: string; answer_mode?: "concise" | "detailed" | "deep"; client_known_state_version?: number }, client: ApiClient = apiClient): Promise<AssistantMessage> {
  return client.post<AssistantMessage>(`/api/v1/runs/${encodeURIComponent(runId)}/assistant/messages`, request);
}

export type AssistantStreamEvent = { event_id: string; run_id: string; conversation_id: string; message_id: string; event_type: string; sequence: number; state_version: number; status: string; correlation_id: string; payload: Record<string, unknown> };

export async function streamAssistantEvents(runId: string, lastEventId: number, signal: AbortSignal, onEvent: (event: AssistantStreamEvent) => void, onHeartbeat: () => void): Promise<never> {
  const response = await fetch(`${getBackendBaseUrl()}/api/v1/runs/${encodeURIComponent(runId)}/assistant/events`, { headers: { ...authenticatedHeaders("text/event-stream"), "Last-Event-ID": String(lastEventId) }, signal, cache: "no-store" });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiClientError(`Assistant event stream failed (${response.status})`, response.status, "GET", "/assistant/events", body || null);
  }
  if (!response.body) throw new Error("Assistant event stream returned no body.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";
  let eventId = "";
  let data: string[] = [];
  const dispatch = () => {
    if (!data.length) return;
    const raw = data.join("\n");
    if (eventName !== "message") {
      const parsed = JSON.parse(raw) as AssistantStreamEvent;
      if (!parsed.event_id && eventId) parsed.event_id = eventId;
      onEvent(parsed);
    }
    eventName = "message"; eventId = ""; data = [];
  };
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) throw new Error("Assistant event stream disconnected.");
      buffer += decoder.decode(chunk.value, { stream: true });
      const lines = buffer.split(/\r?\n/); buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line === "") { dispatch(); continue; }
        if (line.startsWith(":")) { onHeartbeat(); continue; }
        const separator = line.indexOf(":");
        const field = separator < 0 ? line : line.slice(0, separator);
        const value = separator < 0 ? "" : line.slice(separator + 1).replace(/^ /, "");
        if (field === "event") eventName = value;
        else if (field === "id") eventId = value;
        else if (field === "data") data.push(value);
      }
    }
  } finally { reader.cancel().catch(() => undefined); }
}
