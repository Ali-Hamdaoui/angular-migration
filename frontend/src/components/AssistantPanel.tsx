"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAssistantConversation } from "@/hooks/useAssistantConversation";
import { AssistantMessage as AssistantMessageBubble } from "./AssistantMessage";
import { AssistantEvidenceDrawer } from "./AssistantEvidenceDrawer";
import styles from "./ControlTowerShell.module.css";

const baseQuestions = ["Where is the migration now?", "What has already been completed?", "Why is the migration blocked?", "What is the next permitted action?", "How much time, token usage, and estimated cost has the migration consumed?"];
const phaseQuestions: Record<string, string[]> = {
  Analysis: ["What did the Analysis Agent discover?", "Which findings block Planning?", "What evidence supports the reviewer decision?"],
  Planning: ["What did the Planning Agent propose?", "Which changes are highest risk?", "Which commands will validate the plan?"],
  Transformation: ["What changed during Transformation?", "What files changed?", "What remains before Validation?"],
  Validation: ["Which validations passed or failed?", "What is the root cause?", "What is the next permitted action?"],
};

function NextStepNavigation({ targetRoute, runId, label, reason, requiresApproval }: { targetRoute: string; runId: string; label: string; reason: string; requiresApproval: boolean }) {
  const router = useRouter();
  return <div className={styles.note}><button type="button" onClick={() => router.push(targetRoute.replace("{run_id}", encodeURIComponent(runId)))}>{label}</button><small> — {reason}{requiresApproval ? " · human approval required" : ""}</small></div>;
}

export function AssistantPanel({ runId, phase = "unknown", stateVersion = 1, workflowStatus = "unknown" }: { runId: string; phase?: string; stateVersion?: number; workflowStatus?: string }) {
  const [question, setQuestion] = useState("");
  const [answerMode, setAnswerMode] = useState<"concise" | "detailed" | "deep">("concise");
  const { messages, conversationId, state, error, submit } = useAssistantConversation(runId, stateVersion, phase, workflowStatus);
  const suggestions = useMemo(() => [...(phaseQuestions[phase] ?? []), ...baseQuestions].slice(0, 5), [phase]);

  async function onSubmit(event?: FormEvent) {
    event?.preventDefault();
    const value = question.trim();
    if (!value || state === "loading") return;
    try { await submit(value, undefined, answerMode); setQuestion(""); } catch { /* durable failure is rendered from owner state */ }
  }

  return <section className={styles.panel} aria-labelledby="assistant-title">
    <div className={styles.header}><div><p className={styles.kicker}>AMFA-221 · read-only</p><h2 id="assistant-title">Migration Follow-up Assistant</h2></div><span>{stateVersion} · {workflowStatus}{conversationId ? ` · ${conversationId}` : ""}</span></div>
    <p className={styles.note}>Answers are rebuilt from the current workflow projection. Mutations remain governed cockpit actions.</p>
    {state === "loading" && !messages.length ? <p role="status" aria-live="polite">Loading conversation…</p> : null}
    {state === "reconnecting" ? <p role="alert">Refreshing persisted conversation…</p> : null}
    {error ? <p role="alert">{error.code ? `${error.code}: ` : ""}{error.message}{error.correlationId ? ` · ${error.correlationId}` : ""}</p> : null}
    {!messages.length && state !== "loading" ? <p className={styles.note}>Ask a supported migration question.</p> : null}
    <ol aria-label="Assistant conversation" className={styles.list}>{messages.map((message) => <li key={message.message_id} className={styles.previewPanel}>
      <AssistantMessageBubble message={message} />
      <small>Blocker: {message.current_blocker} · Next: {message.next_permitted_action}</small>
      {message.failure_reason ? <p role="alert">Failure: {message.error_code ? `${message.error_code} · ` : ""}{message.failure_reason}{message.correlation_id ? ` · ${message.correlation_id}` : ""}</p> : null}
      {message.role === "assistant" && message.response_status === "failed" ? (() => {
        const original = [...messages].reverse().find((candidate) => candidate.role === "user" && candidate.conversation_id === message.conversation_id && candidate.message_order < message.message_order);
        return <button type="button" aria-label="Retry assistant response" disabled={state === "loading" || !original} onClick={() => { if (original) void submit(original.answer, message.message_id, message.answer_mode || answerMode).catch(() => undefined); }}>Retry</button>;
      })() : null}
      {message.summary ? <p>{message.summary}</p> : null}
      {message.intent ? <small>Intent: {message.intent} · Capability: {message.capability_key || "unavailable"} · Mode: {message.answer_mode || "concise"}</small> : null}
      {message.missing_information?.length ? <small>Missing information: {message.missing_information.join(", ")}</small> : null}
      {message.suggested_follow_ups?.length ? <small>Suggested follow-ups: {message.suggested_follow_ups.join(" · ")}</small> : null}
      <AssistantEvidenceDrawer citations={message.citations ?? []} />
      {(message.next_step_proposals ?? []).map((proposal) => proposal.target_route ? <NextStepNavigation key={proposal.action_key} targetRoute={proposal.target_route} runId={runId} label={proposal.label} reason={proposal.reason} requiresApproval={proposal.requires_human_approval} /> : <div key={proposal.action_key} className={styles.note}><span>{proposal.label}</span><small> — {proposal.reason}{proposal.requires_human_approval ? " · human approval required" : ""}</small></div>)}
      <small>{message.response_status}</small>{message.operational_statistics?.total_tokens == null ? <small>Operational statistics unavailable</small> : <small> · {message.operational_statistics.total_tokens} tokens · {message.operational_statistics.total_cost_usd == null ? "cost unavailable" : `$${message.operational_statistics.total_cost_usd.toFixed(6)}`}</small>}
    </li>)}</ol>
    <div aria-label="Suggested assistant questions" className={styles.list}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setQuestion(suggestion)}>{suggestion}</button>)}</div>
    <form onSubmit={onSubmit}><label htmlFor="assistant-question">Ask about this migration</label><input id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} disabled={state === "loading"} /><select aria-label="Answer mode" value={answerMode} onChange={(event) => setAnswerMode(event.target.value as typeof answerMode)}><option value="concise">Concise</option><option value="detailed">Detailed</option><option value="deep">Deep</option></select><button type="submit" disabled={!question.trim() || state === "loading"}>{state === "loading" ? "Answering…" : "Send"}</button></form>
  </section>;
}
