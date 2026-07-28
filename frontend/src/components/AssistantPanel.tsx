"use client";

import { type FormEvent, type RefObject, useEffect, useMemo, useRef, useState } from "react";
import { getAssistantMessages, sendAssistantMessage } from "@/api/assistant";
import { ApiClientError } from "@/api/client";
import type { AssistantMessage, AssistantAnswerMode } from "@/types/assistant";
import { assistantReplayDecision, replaceAssistantHistory } from "./assistantReplay";
import { AssistantMessage as AssistantMessageBubble } from "./AssistantMessage";
import { AssistantEvidenceDrawer } from "./AssistantEvidenceDrawer";
import { getBackendBaseUrl } from "@/api/client";
import styles from "./ControlTowerShell.module.css";

const baseQuestions = [
  "Explain the current migration state and what is waiting now.",
  "What has already been completed and what remains?",
  "Why is the migration blocked, and what evidence proves it?",
  "What is the next permitted action and why?",
  "Summarize the most important risks, evidence, and operational usage.",
];
const phaseQuestions: Record<string, string[]> = {
  Analysis: ["Summarize the Analysis findings and their evidence.", "Compare the proposer and reviewer conclusions."],
  Planning: ["Explain the current plan, highest risks, and validation commands."],
  Transformation: ["Explain what changed, why it changed, and what remains."],
  Validation: ["Explain every failed validation and the most likely root cause."],
};

function storageKey(runId: string, name: string) {
  return `amfa:assistant:${runId}:${name}`;
}

type PresentationState = "expanded" | "minimized" | "closed";
type AssistantStatus = { pending: boolean; error: boolean; model: string };

function readStorage(key: string) {
  try { return globalThis.localStorage?.getItem(key) ?? null; } catch { return null; }
}

function writeStorage(key: string, value: string) {
  try { globalThis.localStorage?.setItem(key, value); } catch { /* storage is optional */ }
}

function readPresentation(runId: string): PresentationState {
  const stored = readStorage(storageKey(runId, "presentation"));
  if (stored === "expanded" || stored === "minimized" || stored === "closed") return stored;
  return readStorage(storageKey(runId, "open")) === "true" ? "expanded" : "closed";
}

export function AssistantDock(props: { runId: string; phase?: string; stateVersion?: number; workflowStatus?: string }) {
  const [presentation, setPresentation] = useState<PresentationState>(() => readPresentation(props.runId));
  const [status, setStatus] = useState<AssistantStatus>({ pending: false, error: false, model: "Waiting for first answer" });
  const launcherRef = useRef<HTMLButtonElement>(null);
  const restoreRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setPresentation(readPresentation(props.runId));
  }, [props.runId]);

  function changePresentation(next: PresentationState) {
    setPresentation(next);
    writeStorage(storageKey(props.runId, "presentation"), next);
  }

  useEffect(() => {
    (presentation === "expanded" ? closeRef : presentation === "minimized" ? restoreRef : launcherRef).current?.focus();
  }, [presentation]);

  return <div className={styles.assistantDock} data-assistant-presentation={presentation}>
    <div className={`${styles.assistantPopup} ${styles.assistantExpanded}`} role="dialog" aria-modal="false" aria-label="Migration Follow-up Assistant" aria-hidden={presentation !== "expanded"} hidden={presentation !== "expanded"}>
      <AssistantPanel {...props} onClose={() => changePresentation("closed")} onMinimize={() => changePresentation("minimized")} onStatus={setStatus} closeRef={closeRef} />
    </div>
    <div className={styles.assistantMinimized} aria-hidden={presentation !== "minimized"} hidden={presentation !== "minimized"}>
      <span className={styles.assistantIcon} aria-hidden="true">✦</span>
      <span className={styles.assistantMinimizedLabel}><strong>Migration Assistant</strong><small role={status.pending ? "status" : undefined} aria-live="polite">{status.pending ? "Thinking…" : status.error ? "Request failed" : status.model}</small></span>
      {status.pending ? <span className={styles.assistantPending} aria-hidden="true" /> : null}
      {status.error ? <span className={styles.assistantErrorMarker} aria-label="Request failed">!</span> : null}
      <button ref={restoreRef} className={styles.assistantDockButton} type="button" onClick={() => changePresentation("expanded")} aria-label="Expand Assistant">↗</button>
      <button className={styles.assistantDockButton} type="button" onClick={() => changePresentation("closed")} aria-label="Close Assistant">×</button>
    </div>
    <button ref={launcherRef} className={styles.assistantLauncher} type="button" onClick={() => changePresentation("expanded")} aria-expanded={presentation === "expanded"} aria-hidden={presentation !== "closed"} hidden={presentation !== "closed"} aria-label="Open Assistant">
      <span aria-hidden="true">✦</span><span>Ask Assistant</span>
    </button>
  </div>;
}

export function AssistantPanel({ runId, phase = "unknown", stateVersion = 1, workflowStatus = "unknown", onClose, onMinimize, onStatus, closeRef }: { runId: string; phase?: string; stateVersion?: number; workflowStatus?: string; onClose?: () => void; onMinimize?: () => void; onStatus?: (status: AssistantStatus) => void; closeRef?: RefObject<HTMLButtonElement | null> }) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [question, setQuestion] = useState("");
  const [answerMode, setAnswerMode] = useState<AssistantAnswerMode>("concise");
  const [state, setState] = useState<"empty" | "loading" | "ready" | "failed" | "reconnecting">("loading");
  const [error, setError] = useState<string | null>(null);
  const [pendingRequest, setPendingRequest] = useState(false);
  const failedMessageId = useRef<string | undefined>(undefined);
  const retryQuestion = useRef("");
  const submitting = useRef(false);
  const suggestions = useMemo(() => [...(phaseQuestions[phase] ?? []), ...baseQuestions].slice(0, 3), [phase]);
  const activeModel = [...messages].reverse().find((message) => message.role === "assistant")?.model ?? "Waiting for first answer";

  useEffect(() => { onStatus?.({ pending: pendingRequest, error: Boolean(error), model: activeModel }); }, [activeModel, error, onStatus, pendingRequest]);

  useEffect(() => {
    setQuestion(readStorage(storageKey(runId, "draft")) ?? "");
    const storedMode = readStorage(storageKey(runId, "mode"));
    if (storedMode === "concise" || storedMode === "detailed" || storedMode === "deep") setAnswerMode(storedMode);
  }, [runId]);

  useEffect(() => {
    let active = true;
    setState("loading");
    getAssistantMessages(runId).then((history) => {
      if (!active) return;
      setMessages(replaceAssistantHistory([], history.messages));
      setConversationId(history.conversation_id);
      setState(history.messages.length ? "ready" : "empty");
    }).catch(() => {
      if (active) {
        setError("Conversation could not be restored. Retry to reconnect.");
        setState("reconnecting");
      }
    });
    return () => { active = false; };
  }, [runId]);

  useEffect(() => {
    let active = true;
    let lastSequence = 0;
    if (typeof window === "undefined" || typeof EventSource === "undefined") return () => { active = false; };
    const source = new EventSource(`${getBackendBaseUrl()}/api/v1/runs/${encodeURIComponent(runId)}/assistant/events?last_event_id=0`);
    const restore = () => getAssistantMessages(runId).then((history) => {
      if (!active) return;
      setMessages((current) => replaceAssistantHistory(current, history.messages).concat(current.filter((message) => message.message_id.startsWith("optimistic-") && !history.messages.some((restored) => restored.request_id === message.request_id))));
      setConversationId(history.conversation_id);
      setState(history.messages.length ? "ready" : "empty");
    }).catch(() => { if (active) setState("reconnecting"); });
    const onLifecycle = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as { sequence: number; event_type: string };
        const decision = assistantReplayDecision(lastSequence, payload);
        if (decision === "ignore") return;
        if (decision === "gap") { setState("reconnecting"); void restore(); return; }
        lastSequence = payload.sequence;
        if (payload.event_type !== "ASSISTANT_RESPONSE_STARTED") void restore();
      } catch { setState("reconnecting"); void restore(); }
    };
    const lifecycleEvents = ["ASSISTANT_RESPONSE_STARTED", "ASSISTANT_RESPONSE_COMPLETED", "ASSISTANT_RESPONSE_FAILED"] as const;
    lifecycleEvents.forEach((eventName) => source.addEventListener(eventName, onLifecycle));
    source.onerror = () => { if (active) { setState("reconnecting"); void restore(); } };
    return () => { active = false; lifecycleEvents.forEach((eventName) => source.removeEventListener(eventName, onLifecycle)); source.close(); };
  }, [runId]);

  function updateQuestion(value: string) {
    setQuestion(value);
    writeStorage(storageKey(runId, "draft"), value);
  }

  function updateAnswerMode(value: AssistantAnswerMode) {
    setAnswerMode(value);
    writeStorage(storageKey(runId, "mode"), value);
  }

  async function submit(event?: FormEvent, retryOfMessageId?: string) {
    event?.preventDefault();
    const value = question.trim() || retryQuestion.current;
    if (!value || state === "loading" || submitting.current) return;
    submitting.current = true;
    setState("loading");
    setError(null);
    const requestId = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const optimistic: AssistantMessage = {
      message_id: `optimistic-${requestId}`, model: "user", message_order: messages.length + 1,
      conversation_id: conversationId ?? "pending", run_id: runId, role: "user", answer: value,
      current_phase: phase, current_stage: "unknown", workflow_status: workflowStatus, current_gate: "unknown",
      current_blocker: "unknown", next_permitted_action: "unknown", workflow_state_version: stateVersion,
      stale: false, evidence_references: [], proof_label: "user request",
      usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 },
      response_status: "pending", failure_reason: null, request_id: requestId, retry_of_message_id: retryOfMessageId,
    };
    failedMessageId.current = undefined;
    retryQuestion.current = value;
    setPendingRequest(true);
    setMessages((current) => [...current, optimistic]);
    updateQuestion("");
    try {
      const result = await sendAssistantMessage(runId, {
        message: value, conversation_id: conversationId, request_id: requestId, idempotency_key: requestId, retry_of_message_id: retryOfMessageId,
        answer_mode: answerMode, client_known_state_version: stateVersion,
      });
      setConversationId(result.conversation_id);
      setMessages((current) => [...current.filter((item) => item.message_id !== optimistic.message_id), result]);
      retryQuestion.current = "";
      setPendingRequest(false);
      setState("ready");
    } catch (reason) {
      failedMessageId.current = optimistic.message_id;
      setMessages((current) => current.map((item) => item.message_id === optimistic.message_id ? { ...item, response_status: "failed", failure_reason: reason instanceof Error ? reason.message : "Request failed" } : item));
      setPendingRequest(false);
      setError(reason instanceof ApiClientError ? `${reason.method} ${reason.path} returned ${reason.status}` : reason instanceof Error ? reason.message : "The Assistant could not answer. Retry while the read-only cockpit remains available.");
      setState("failed");
    } finally {
      submitting.current = false;
    }
  }

  return <section className={styles.assistantPanel} aria-labelledby="assistant-title">
    <div className={styles.assistantHeader}><div><p className={styles.kicker}>AMFA-221 · read-only</p><h2 id="assistant-title">Migration Follow-up Assistant</h2></div><div className={styles.assistantBadges}><span>State {stateVersion}</span><span>{workflowStatus}</span><span>Model: {activeModel}</span><div className={styles.assistantControls}>{onMinimize ? <button className={styles.assistantClose} type="button" onClick={onMinimize} aria-label="Minimize Assistant">—</button> : null}{onClose ? <button ref={closeRef} className={styles.assistantClose} type="button" onClick={onClose} aria-label="Close Assistant">×</button> : null}</div></div></div>
    <div className={styles.assistantInfo}><p className={styles.note}>Answers use the current backend projection, validated immutable evidence, and this run&apos;s persisted conversation. Mutations remain governed cockpit actions.</p>
    {state === "loading" && !messages.length && !pendingRequest ? <p role="status" aria-live="polite">Loading conversation…</p> : null}
    {pendingRequest ? <p role="status" aria-live="polite">Assistant is thinking…</p> : null}
    {state === "reconnecting" ? <p role="alert">Reconnecting to persisted conversation…</p> : null}
    {error ? <div className={styles.assistantError} role="alert"><strong>Assistant request failed</strong><span> {error}</span></div> : null}
    {!messages.length && state !== "loading" ? <p className={styles.note}>Ask any read-only question about this migration.</p> : null}</div>
    <div className={styles.assistantConversationRegion} role="region" tabIndex={0} aria-label="Assistant conversation">
      <ol className={styles.assistantConversation}>{messages.map((message) => <li key={message.message_id} className={styles.assistantConversationItem}><AssistantMessageBubble message={message} />{message.role === "assistant" ? <><div className={styles.assistantMessageMeta}><span>Blocker: {message.current_blocker}</span><span>Next: {message.next_permitted_action}</span></div><AssistantEvidenceDrawer evidence={message.evidence_references} /><small>{message.operational_statistics?.total_tokens == null ? "Operational statistics unavailable" : `${message.operational_statistics.total_tokens} tokens · ${message.operational_statistics.total_cost_usd == null ? "cost unavailable" : `$${message.operational_statistics.total_cost_usd.toFixed(6)}`}`}</small></> : null}</li>)}{pendingRequest ? <li key="assistant-pending" className={styles.assistantConversationItem} aria-live="polite"><article data-role="assistant" aria-label="Assistant is thinking"><small>assistant</small><p>Thinking…</p></article></li> : null}</ol>
      <div aria-label="Suggested assistant questions" className={styles.assistantSuggestions}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => updateQuestion(suggestion)}>{suggestion}</button>)}</div>
    </div>
    <form className={styles.assistantComposer} onSubmit={submit}><label htmlFor="assistant-question">Ask about this migration</label><textarea id="assistant-question" rows={3} value={question} onChange={(event) => updateQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }} disabled={state === "loading"} /><div><label htmlFor="assistant-answer-mode">Answer depth</label><select id="assistant-answer-mode" value={answerMode} onChange={(event) => updateAnswerMode(event.target.value as AssistantAnswerMode)}><option value="concise">Concise</option><option value="detailed">Detailed</option><option value="deep">Deep</option></select><button type="submit" disabled={!question.trim() || state === "loading"}>{state === "loading" ? "Answering…" : "Send"}</button>{state === "failed" ? <button type="button" onClick={() => void submit(undefined, failedMessageId.current)}>Retry</button> : null}</div></form>
  </section>;
}
