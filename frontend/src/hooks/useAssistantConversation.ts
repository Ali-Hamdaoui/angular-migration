import { useCallback, useEffect, useState } from "react";
import { getAssistantMessages, sendAssistantMessage } from "@/api/assistant";
import type { AssistantMessage } from "@/types/assistant";
import { replaceAssistantHistory } from "@/components/assistantReplay";

const id = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;

export function useAssistantConversation(runId: string, stateVersion: number) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [state, setState] = useState<"empty" | "loading" | "ready" | "failed" | "reconnecting">("loading");
  const [error, setError] = useState<string | null>(null);
  const restore = useCallback(async () => { const history = await getAssistantMessages(runId, conversationId); setMessages((current) => replaceAssistantHistory(current, history.messages)); setConversationId(history.conversation_id); setState(history.messages.length ? "ready" : "empty"); }, [conversationId, runId]);
  useEffect(() => { let active = true; setState("loading"); getAssistantMessages(runId).then((history) => { if (!active) return; setMessages(history.messages); setConversationId(history.conversation_id); setState(history.messages.length ? "ready" : "empty"); }).catch(() => { if (active) { setError("Conversation could not be restored."); setState("reconnecting"); } }); return () => { active = false; }; }, [runId]);
  const submit = useCallback(async (message: string, retryOfMessageId?: string) => {
    const requestId = id();
    const optimistic: AssistantMessage = { message_id: `optimistic-${requestId}`, message_order: messages.length + 1, conversation_id: conversationId ?? "pending", run_id: runId, role: "user", answer: message, current_phase: "unknown", current_stage: "unknown", workflow_status: "unknown", current_gate: "unknown", current_blocker: "unknown", next_permitted_action: "unknown", workflow_state_version: stateVersion, stale: false, evidence_references: [], proof_label: "user request", usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 }, response_status: "pending", failure_reason: null, request_id: requestId, retry_of_message_id: retryOfMessageId };
    setMessages((current) => [...current, optimistic]); setState("loading"); setError(null);
    try { const result = await sendAssistantMessage(runId, { message, conversation_id: conversationId, request_id: requestId, idempotency_key: requestId, retry_of_message_id: retryOfMessageId, client_known_state_version: stateVersion }); setConversationId(result.conversation_id); setMessages((current) => [...current.filter((item) => item.message_id !== optimistic.message_id), result]); setState("ready"); return result; } catch (reason) { setError(reason instanceof Error ? reason.message : "The Assistant could not answer."); setState("failed"); throw reason; }
  }, [conversationId, messages.length, runId, stateVersion]);
  return { messages, conversationId, state, error, submit, restore, setState, setMessages };
}
