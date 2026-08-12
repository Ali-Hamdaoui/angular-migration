import { useCallback, useEffect, useRef, useState } from "react";
import { getAssistantMessages, sendAssistantMessage, streamAssistantEvents, type AssistantStreamEvent } from "@/api/assistant";
import { ApiClientError } from "@/api/client";
import type { AssistantHistory, AssistantMessage } from "@/types/assistant";
import { assistantReplayDecision } from "@/components/assistantReplay";

const id = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
const conversationParam = "conversation_id";

type AssistantErrorState = { code?: string; message: string; correlationId?: string | null; details?: { conversation_id?: string; message_id?: string; request_id?: string } };

function stableError(reason: unknown): AssistantErrorState {
  if (reason instanceof ApiClientError && reason.responseBody) {
    try {
      const body = JSON.parse(reason.responseBody) as { error_code?: string; message?: string; correlation_id?: string; details?: { conversation_id?: string; message_id?: string; request_id?: string } };
      return { code: body.error_code, message: body.message || reason.message, correlationId: body.correlation_id, details: body.details };
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
  const [error, setError] = useState<AssistantErrorState | null>(null);
  const lastTransportOperation = useRef<{ request: Parameters<typeof sendAssistantMessage>[1] } | undefined>(undefined);
  const previousStateVersion = useRef(stateVersion);
  const inFlight = useRef(false);
  const cursor = useRef(0);
  const cursorRun = useRef(runId);
  const eventPayloads = useRef(new Map<number, string>());
  const gapEpisode = useRef(false);
  const reconnectAfterRecovery = useRef(false);
  const historyReloadInFlight = useRef<Promise<AssistantHistory> | null>(null);
  const lastHistoryReload = useRef<{ at: number; conversationId?: string; history: AssistantHistory } | null>(null);

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
  const conversationRef = useRef(conversationId);
  conversationRef.current = conversationId;
  const reloadHistory = useCallback((selectedConversationId?: string, force = false) => {
    if (historyReloadInFlight.current) return historyReloadInFlight.current;
    const recent = lastHistoryReload.current;
    if (!force && recent && recent.conversationId === selectedConversationId && Date.now() - recent.at < 250) return Promise.resolve(recent.history);
    const operation = restore(selectedConversationId).then((history) => {
      lastHistoryReload.current = { at: Date.now(), conversationId: selectedConversationId, history };
      return history;
    }).finally(() => { historyReloadInFlight.current = null; });
    historyReloadInFlight.current = operation;
    return operation;
  }, [restore]);
  const reloadHistoryRef = useRef(reloadHistory);
  reloadHistoryRef.current = reloadHistory;

  useEffect(() => {
    let active = true;
    if (cursorRun.current !== runId) {
      cursor.current = 0;
      eventPayloads.current.clear();
      gapEpisode.current = false;
      cursorRun.current = runId;
    }
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
    void reloadHistoryRef.current(conversationId).catch(() => setState("reconnecting"));
  }, [conversationId, stateVersion]);

  useEffect(() => {
    let active = true;
    let controller: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = 100;
    const refresh = async () => {
      if (!active) return;
      setState("reconnecting");
      try { await reloadHistoryRef.current(conversationRef.current || urlConversationId(), true); gapEpisode.current = false; }
      catch { /* bounded reconnect loop retains durable messages */ }
    };
    const handleEvent = (event: AssistantStreamEvent) => {
      if (!active) return;
      const decision = assistantReplayDecision(cursor.current, event);
      const fingerprint = JSON.stringify(event);
      if (decision === "ignore") {
        if (event.sequence === cursor.current && eventPayloads.current.get(event.sequence) !== fingerprint) {
          gapEpisode.current = true;
          reconnectAfterRecovery.current = true;
          void refresh().finally(() => controller?.abort());
        }
        return;
      }
      if (decision === "gap") {
        if (!gapEpisode.current) { gapEpisode.current = true; reconnectAfterRecovery.current = true; void refresh().finally(() => controller?.abort()); }
        return;
      }
      cursor.current = event.sequence;
      eventPayloads.current.set(event.sequence, fingerprint);
      delay = 100;
      if (event.event_type === "ASSISTANT_RESPONSE_COMPLETED" || event.event_type === "ASSISTANT_RESPONSE_FAILED") void reloadHistoryRef.current(conversationRef.current || urlConversationId(), true).catch(() => setState("reconnecting"));
    };
    const connect = async () => {
      while (active) {
        controller = new AbortController();
        try {
          setState((current) => current === "loading" ? current : "ready");
          await streamAssistantEvents(runId, cursor.current, controller.signal, handleEvent, () => { delay = 100; });
        } catch (reason) {
          if (!active) return;
          if (reason instanceof DOMException && reason.name === "AbortError" && !reconnectAfterRecovery.current) return;
          reconnectAfterRecovery.current = false;
          if (reason instanceof ApiClientError && (reason.status === 401 || reason.status === 403)) { setError(stableError(reason)); setState("failed"); return; }
          setState("reconnecting");
          await new Promise<void>((resolve) => { timer = setTimeout(resolve, delay); });
          delay = Math.min(delay * 2, 2000);
        }
      }
    };
    void connect();
    return () => { active = false; controller?.abort(); if (timer) clearTimeout(timer); };
  }, [runId]);

  const submit = useCallback(async (message: string, retryOfMessageId?: string, answerMode?: "concise" | "detailed" | "deep") => {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    const requestId = id();
    const idempotencyKey = id();
    const optimistic: AssistantMessage = {
      message_id: `optimistic-${requestId}`, message_order: messages.length + 1,
      conversation_id: conversationId ?? "pending", run_id: runId, role: "user", answer: message,
      current_phase: phase, current_stage: "unknown", workflow_status: workflowStatus, current_gate: "unknown",
      current_blocker: "unknown", next_permitted_action: "unknown", workflow_state_version: stateVersion,
      stale: false, evidence_references: [], proof_label: "user request",
      usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 },
      response_status: "pending", failure_reason: null, request_id: requestId, retry_of_message_id: retryOfMessageId,
    };
    const operation = { message, conversation_id: conversationId, request_id: requestId, idempotency_key: idempotencyKey, retry_of_message_id: retryOfMessageId, answer_mode: answerMode, client_known_state_version: stateVersion };
    lastTransportOperation.current = { request: operation };
    setMessages((current) => [...current, optimistic]); setState("loading"); setError(null);
    try {
      const result = await sendAssistantMessage(runId, operation);
       await reloadHistory(result.conversation_id);
      return result;
    } catch (reason) {
      const parsed = stableError(reason);
      setError(parsed);
      const selectedConversation = parsed.details?.conversation_id || conversationId;
      if (selectedConversation) {
         try { await reloadHistory(selectedConversation); } catch { /* the durable error remains available on the next reload */ }
      }
      setState("failed");
      throw reason;
    } finally {
      inFlight.current = false;
    }
  }, [conversationId, messages.length, phase, reloadHistory, runId, stateVersion, workflowStatus]);

  const retryTransport = useCallback(async () => {
    const operation = lastTransportOperation.current;
    if (!operation) throw new Error("No Assistant transport operation is available to retry.");
    const result = await sendAssistantMessage(runId, operation.request);
    await reloadHistory(result.conversation_id);
    return result;
  }, [reloadHistory, runId]);

  return { messages, conversationId, state, error, submit, retryTransport, restore, setState, setMessages };
}
