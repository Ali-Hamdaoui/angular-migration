"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { getAssistantMessages, sendAssistantMessage } from "@/api/assistant";
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

export function AssistantDock(props: { runId: string; phase?: string; stateVersion?: number; workflowStatus?: string }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(globalThis.localStorage?.getItem(storageKey(props.runId, "open")) === "true");
  }, [props.runId]);

  function changeOpen(next: boolean) {
    setOpen(next);
    globalThis.localStorage?.setItem(storageKey(props.runId, "open"), String(next));
  }

  return <div className={styles.assistantDock}>
    <div className={styles.assistantPopup} role="dialog" aria-modal="false" aria-label="Migration Follow-up Assistant" hidden={!open}>
      <button className={styles.assistantClose} type="button" onClick={() => changeOpen(false)} aria-label="Close Assistant">×</button>
      <AssistantPanel {...props} />
    </div>
    <button className={styles.assistantLauncher} type="button" onClick={() => changeOpen(!open)} aria-expanded={open} aria-label={open ? "Hide Assistant" : "Open Assistant"}>
      <span aria-hidden="true">✦</span><span>{open ? "Hide Assistant" : "Ask Assistant"}</span>
    </button>
  </div>;
}

export function AssistantPanel({ runId, phase = "unknown", stateVersion = 1, workflowStatus = "unknown" }: { runId: string; phase?: string; stateVersion?: number; workflowStatus?: string }) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [question, setQuestion] = useState("");
  const [answerMode, setAnswerMode] = useState<AssistantAnswerMode>("concise");
  const [state, setState] = useState<"empty" | "loading" | "ready" | "failed" | "reconnecting">("loading");
  const [error, setError] = useState<string | null>(null);
  const suggestions = useMemo(() => [...(phaseQuestions[phase] ?? []), ...baseQuestions].slice(0, 5), [phase]);
  const activeModel = [...messages].reverse().find((message) => message.role === "assistant")?.model ?? "Waiting for first answer";

  useEffect(() => {
    setQuestion(globalThis.localStorage?.getItem(storageKey(runId, "draft")) ?? "");
    const storedMode = globalThis.localStorage?.getItem(storageKey(runId, "mode"));
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
      setMessages((current) => replaceAssistantHistory(current, history.messages));
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
    globalThis.localStorage?.setItem(storageKey(runId, "draft"), value);
  }

  function updateAnswerMode(value: AssistantAnswerMode) {
    setAnswerMode(value);
    globalThis.localStorage?.setItem(storageKey(runId, "mode"), value);
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const value = question.trim();
    if (!value || state === "loading") return;
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
      response_status: "pending", failure_reason: null, request_id: requestId,
    };
    setMessages((current) => [...current, optimistic]);
    try {
      const result = await sendAssistantMessage(runId, {
        message: value, conversation_id: conversationId, request_id: requestId, idempotency_key: requestId,
        answer_mode: answerMode, client_known_state_version: stateVersion,
      });
      setConversationId(result.conversation_id);
      setMessages((current) => [...current.filter((item) => item.message_id !== optimistic.message_id), result]);
      updateQuestion("");
      setState("ready");
    } catch (reason) {
      setMessages((current) => current.filter((item) => item.message_id !== optimistic.message_id));
      setError(reason instanceof Error ? reason.message : "The Assistant could not answer. Retry while the read-only cockpit remains available.");
      setState("failed");
    }
  }

  return <section className={styles.assistantPanel} aria-labelledby="assistant-title">
    <div className={styles.assistantHeader}><div><p className={styles.kicker}>AMFA-221 · read-only</p><h2 id="assistant-title">Migration Follow-up Assistant</h2></div><div className={styles.assistantBadges}><span>State {stateVersion}</span><span>{workflowStatus}</span><span>Model: {activeModel}</span></div></div>
    <p className={styles.note}>Answers use the current backend projection, validated immutable evidence, and this run&apos;s persisted conversation. Mutations remain governed cockpit actions.</p>
    {state === "loading" && !messages.length ? <p role="status" aria-live="polite">Loading conversation…</p> : null}
    {state === "reconnecting" ? <p role="alert">Reconnecting to persisted conversation…</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {!messages.length && state !== "loading" ? <p className={styles.note}>Ask any read-only question about this migration.</p> : null}
    <ol aria-label="Assistant conversation" className={styles.assistantConversation}>{messages.map((message) => <li key={message.message_id} className={styles.assistantConversationItem}><AssistantMessageBubble message={message} /><div className={styles.assistantMessageMeta}><span>Blocker: {message.current_blocker}</span><span>Next: {message.next_permitted_action}</span></div><AssistantEvidenceDrawer evidence={message.evidence_references} /><small>{message.operational_statistics?.total_tokens == null ? "Operational statistics unavailable" : `${message.operational_statistics.total_tokens} tokens · ${message.operational_statistics.total_cost_usd == null ? "cost unavailable" : `$${message.operational_statistics.total_cost_usd.toFixed(6)}`}`}</small></li>)}</ol>
    <div aria-label="Suggested assistant questions" className={styles.assistantSuggestions}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => updateQuestion(suggestion)}>{suggestion}</button>)}</div>
    <form className={styles.assistantComposer} onSubmit={submit}><label htmlFor="assistant-question">Ask about this migration</label><textarea id="assistant-question" rows={3} value={question} onChange={(event) => updateQuestion(event.target.value)} disabled={state === "loading"} /><div><label htmlFor="assistant-answer-mode">Answer depth</label><select id="assistant-answer-mode" value={answerMode} onChange={(event) => updateAnswerMode(event.target.value as AssistantAnswerMode)}><option value="concise">Concise</option><option value="detailed">Detailed</option><option value="deep">Deep</option></select><button type="submit" disabled={!question.trim() || state === "loading"}>{state === "loading" ? "Answering…" : "Send"}</button>{state === "failed" ? <button type="button" onClick={() => void submit()}>Retry</button> : null}</div></form>
  </section>;
}
