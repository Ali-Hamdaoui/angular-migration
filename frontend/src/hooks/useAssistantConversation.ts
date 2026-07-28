import { useCallback, useEffect, useRef, useState } from "react";
import { getAssistantMessages, sendAssistantMessage } from "@/api/assistant";
import { ApiClientError, getBackendBaseUrl } from "@/api/client";
import type { AssistantHistory, AssistantMessage } from "@/types/assistant";
import { assistantReplayDecision } from "@/components/assistantReplay";

const id = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
const conversationParam = "conversation_id";

function stableError(reason: unknown) {
  if (reason instanceof ApiClientError && reason.responseBody) {
    try {
      const body = JSON.parse(reason.responseBody) as { error_code?: string; message?: string; correlation_id?: string };
      return { code: body.error_code, message: body.message || reason.message, correlationId: body.correlation_id };
    } catch { /* keep the sanitized transport message */ }
  }
  return { message: reason instanceof Error ? reason.message : "The Assistant could not answer." };
}

function urlConversationId(): string | undefined {
  if (typeof window === "undefined") return undefined;
  return new URL(window.location.href).searchParams.get(conversationParam)?.trim() || undefined;
}

function replaceUrlConversationId(value?: string) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(conversationParam, value);
  else url.searchParams.delete(conversationParam);
  window.history.replaceState(window.history.state, "", url);
}

export function useAssistantConversation(runId: string, stateVersion: number, phase = "unknown", workflowStatus = "unknown") {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [state, setState] = useState<"empty" | "loading" | "ready" | "failed" | "reconnecting">("loading");
  const [error, setError] = useState<{ code?: string; message: string; correlationId?: string | null } | null>(null);
  const previousStateVersion = useRef(stateVersion);

  const adoptHistory = useCallback((history: AssistantHistory) => {
    setMessages(history.messages);
    setConversationId(history.conversation_id);
    replaceUrlConversationId(history.conversation_id);
    setState(history.messages.length ? "ready" : "empty");
  }, []);

  const restore = useCallback(async (selectedConversationId = conversationId) => {
    const history = await getAssistantMessages(runId, selectedConversationId);
    adoptHistory(history);
    return history;
  }, [adoptHistory, conversationId, runId]);

  useEffect(() => {
    let active = true;
    setState("loading");
    setError(null);
    const selected = urlConversationId();
    getAssistantMessages(runId, selected).then((history) => { if (active) adoptHistory(history); }).catch(() => {
      if (active) { setError({ message: "Conversation could not be restored." }); setState("reconnecting"); }
    });
    return () => { active = false; };
  }, [adoptHistory, runId]);

  useEffect(() => {
    if (previousStateVersion.current === stateVersion) return;
    previousStateVersion.current = stateVersion;
    if (!conversationId) return;
    void restore(conversationId).catch(() => setState("reconnecting"));
  }, [conversationId, restore, stateVersion]);

  useEffect(() => {
    let active = true;
    let lastSequence = 0;
    if (typeof window === "undefined" || typeof EventSource === "undefined") return () => { active = false; };
    const source = new EventSource(`${getBackendBaseUrl()}/api/v1/runs/${encodeURIComponent(runId)}/assistant/events?last_event_id=${lastSequence}`);
    const refresh = () => restore(conversationId || urlConversationId()).catch(() => { if (active) setState("reconnecting"); });
    const onLifecycle = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as { sequence: number; event_type: string };
        const decision = assistantReplayDecision(lastSequence, payload);
        if (decision === "ignore") return;
        if (decision === "gap") { setState("reconnecting"); void refresh(); return; }
        lastSequence = payload.sequence;
        if (payload.event_type !== "ASSISTANT_RESPONSE_STARTED") void refresh();
      } catch { setState("reconnecting"); void refresh(); }
    };
    const lifecycleEvents = ["ASSISTANT_RESPONSE_STARTED", "ASSISTANT_RESPONSE_COMPLETED", "ASSISTANT_RESPONSE_FAILED"];
    lifecycleEvents.forEach((name) => source.addEventListener(name, onLifecycle));
    source.onerror = () => { if (active) { setState("reconnecting"); void refresh(); } };
    return () => { active = false; lifecycleEvents.forEach((name) => source.removeEventListener(name, onLifecycle)); source.close(); };
  }, [conversationId, restore, runId]);

  const submit = useCallback(async (message: string, retryOfMessageId?: string, answerMode?: "concise" | "detailed" | "deep") => {
    const requestId = id();
    const optimistic: AssistantMessage = {
      message_id: `optimistic-${requestId}`, message_order: messages.length + 1,
      conversation_id: conversationId ?? "pending", run_id: runId, role: "user", answer: message,
      current_phase: phase, current_stage: "unknown", workflow_status: workflowStatus, current_gate: "unknown",
      current_blocker: "unknown", next_permitted_action: "unknown", workflow_state_version: stateVersion,
      stale: false, evidence_references: [], proof_label: "user request",
      usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 },
      response_status: "pending", failure_reason: null, request_id: requestId, retry_of_message_id: retryOfMessageId,
    };
    setMessages((current) => [...current, optimistic]); setState("loading"); setError(null);
    try {
      const result = await sendAssistantMessage(runId, { message, conversation_id: conversationId, request_id: requestId, idempotency_key: requestId, retry_of_message_id: retryOfMessageId, answer_mode: answerMode, client_known_state_version: stateVersion });
      setConversationId(result.conversation_id); replaceUrlConversationId(result.conversation_id);
      setMessages((current) => [...current.filter((item) => item.message_id !== optimistic.message_id), result]); setState("ready"); return result;
    } catch (reason) {
      setError(stableError(reason)); setState("failed");
      throw reason;
    }
  }, [conversationId, messages.length, phase, runId, stateVersion, workflowStatus]);

  return { messages, conversationId, state, error, submit, restore, setState, setMessages };
}
