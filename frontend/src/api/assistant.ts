import { apiClient, type createApiClient } from "./client";
import type { AssistantHistory, AssistantMessage } from "@/types/assistant";

type ApiClient = ReturnType<typeof createApiClient>;
export function getAssistantMessages(runId: string, conversationId?: string, client: ApiClient = apiClient): Promise<AssistantHistory> {
  const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : "";
  return client.get<AssistantHistory>(`/api/v1/runs/${encodeURIComponent(runId)}/assistant/messages${query}`);
}
export function sendAssistantMessage(runId: string, request: { message: string; conversation_id?: string; idempotency_key: string; client_known_state_version?: number }, client: ApiClient = apiClient): Promise<AssistantMessage> {
  return client.post<AssistantMessage>(`/api/v1/runs/${encodeURIComponent(runId)}/assistant/messages`, request);
}
