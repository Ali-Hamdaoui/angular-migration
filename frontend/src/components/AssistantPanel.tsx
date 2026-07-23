"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { getAssistantMessages, sendAssistantMessage } from "@/api/assistant";
import type { AssistantMessage } from "@/types/assistant";
import { assistantReplayDecision, replaceAssistantHistory } from "./assistantReplay";
import { getBackendBaseUrl } from "@/api/client";
import styles from "./ControlTowerShell.module.css";

const baseQuestions = ["Where is the migration now?", "What has already been completed?", "Why is the migration blocked?", "What is the next permitted action?", "How much time, token usage, and estimated cost has the migration consumed?"];
const phaseQuestions: Record<string, string[]> = {
  Analysis: ["What did the Analysis Agent discover?", "Which findings block Planning?", "What evidence supports the reviewer decision?"],
  Planning: ["What did the Planning Agent propose?", "Which changes are highest risk?", "Which commands will validate the plan?"],
  Transformation: ["What changed during Transformation?", "What files changed?", "What remains before Validation?"],
  Validation: ["Which validations passed or failed?", "What is the root cause?", "What is the next permitted action?"],
};

export function AssistantPanel({ runId, phase = "unknown", stateVersion = 1, workflowStatus = "unknown" }: { runId: string; phase?: string; stateVersion?: number; workflowStatus?: string }) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<"empty" | "loading" | "ready" | "failed" | "reconnecting">("loading");
  const [error, setError] = useState<string | null>(null);
  const suggestions = useMemo(() => [...(phaseQuestions[phase] ?? []), ...baseQuestions].slice(0, 5), [phase]);

  useEffect(() => {
    let active = true;
    setState("loading");
    getAssistantMessages(runId).then((history) => { if (!active) return; setMessages(replaceAssistantHistory([], history.messages)); setConversationId(history.conversation_id); setState(history.messages.length ? "ready" : "empty"); }).catch(() => { if (active) { setError("Conversation could not be restored. Retry to reconnect."); setState("reconnecting"); } });
    return () => { active = false; };
  }, [runId]);

  useEffect(() => {
    let active = true;
    let lastSequence = 0;
    if (typeof window === "undefined" || typeof EventSource === "undefined") return () => { active = false; };
    const source = new EventSource(`${getBackendBaseUrl()}/api/v1/runs/${encodeURIComponent(runId)}/assistant/events`);
    const restore = () => getAssistantMessages(runId, conversationId).then((history) => { if (!active) return; setMessages((current) => replaceAssistantHistory(current, history.messages)); setConversationId(history.conversation_id); setState(history.messages.length ? "ready" : "empty"); }).catch(() => { if (active) setState("reconnecting"); });
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
    source.onmessage = onLifecycle;
    source.onerror = () => { if (active) { setState("reconnecting"); void restore(); } };
    return () => { active = false; source.close(); };
  }, [runId, conversationId, stateVersion]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const value = question.trim();
    if (!value || state === "loading") return;
    setState("loading"); setError(null);
    const idempotencyKey = `${runId}-${conversationId ?? "new"}-${value}`.slice(0, 128);
    try {
      const result = await sendAssistantMessage(runId, { message: value, conversation_id: conversationId, idempotency_key: idempotencyKey, client_known_state_version: stateVersion });
      setConversationId(result.conversation_id); setMessages((current) => current.some((item) => item.message_id === result.message_id) ? current : [...current, result]); setQuestion(""); setState("ready");
    } catch { setError("The Assistant could not answer. Retry while the read-only cockpit remains available."); setState("failed"); }
  }

  return <section className={styles.panel} aria-labelledby="assistant-title">
    <div className={styles.header}><div><p className={styles.kicker}>AMFA-221 · read-only</p><h2 id="assistant-title">Migration Follow-up Assistant</h2></div><span>{stateVersion} · {workflowStatus}</span></div>
    <p className={styles.note}>Answers are rebuilt from the current workflow projection. Mutations remain governed cockpit actions.</p>
    {state === "loading" && !messages.length ? <p role="status" aria-live="polite">Loading conversation…</p> : null}
    {state === "reconnecting" ? <p role="alert">Reconnecting to persisted conversation…</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {!messages.length && state !== "loading" ? <p className={styles.note}>Ask a supported migration question.</p> : null}
    <ol aria-label="Assistant conversation" className={styles.list}>{messages.map((message) => <li key={message.message_id} className={styles.previewPanel}><p>{message.answer}</p><small>{message.current_phase} · {message.current_stage} · {message.current_gate} · {message.proof_label} · state version {message.workflow_state_version}{message.stale ? " · stale answer" : ""}</small>{message.evidence_references.length ? <div><span>Evidence:</span><ul aria-label="Evidence references">{message.evidence_references.map((evidence) => <li key={evidence.artifact_id}><a className={styles.actionLink} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(evidence.artifact_id)}`} target="_blank" rel="noreferrer">{evidence.label}</a></li>)}</ul></div> : null}<small>{message.usage.total_tokens} tokens · ${message.usage.estimated_total_cost.toFixed(6)}</small></li>)}</ol>
    <div aria-label="Suggested assistant questions" className={styles.list}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setQuestion(suggestion)}>{suggestion}</button>)}</div>
    <form onSubmit={submit}><label htmlFor="assistant-question">Ask about this migration</label><input id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} disabled={state === "loading"} /><button type="submit" disabled={!question.trim() || state === "loading"}>{state === "loading" ? "Answering…" : "Send"}</button>{state === "failed" ? <button type="button" onClick={() => void submit()}>Retry</button> : null}</form>
  </section>;
}
