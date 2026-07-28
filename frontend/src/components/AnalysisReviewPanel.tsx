"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import { decideG04, generateAnalysis, getAnalysis, retryAnalysis } from "@/api/analysis";
import { createLogicalOperationKeys } from "@/lib/idempotency";
import type { AnalysisResponse, G04Decision } from "@/types/analysis";
import type { ArtifactRefDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

const decisions: Array<{ value: G04Decision; label: string }> = [
  { value: "approve", label: "Approve G04" },
  { value: "approve_with_comment", label: "Approve with comment" },
  { value: "request_modification", label: "Request modification" },
  { value: "reject", label: "Reject G04" },
];
const ANALYSIS_EVENTS = ["ANALYSIS_AGENT_STARTED", "ANALYSIS_AGENT_COMPLETED", "ANALYSIS_AGENT_FAILED", "ANALYSIS_REVIEWER_STARTED", "ANALYSIS_REVIEWER_COMPLETED", "ANALYSIS_REVIEWER_FAILED", "ANALYSIS_INPUT_VALIDATION_STARTED", "ANALYSIS_INPUT_VALIDATION_COMPLETED", "ANALYSIS_CONTEXT_PREPARED", "LLM_REQUEST_PREPARED", "LLM_HTTP_REQUEST_STARTED", "LLM_HTTP_RESPONSE_RECEIVED", "LLM_RESPONSE_DECODED", "LLM_STRUCTURED_OUTPUT_VALIDATED", "G04_CREATED", "G04_APPROVED", "G04_MODIFICATION_REQUESTED", "G04_REJECTED", "G04_STALE"];

function correlationFrom(error: ApiClientError) {
  try { return (JSON.parse(error.responseBody ?? "{}") as { correlation_id?: string }).correlation_id ?? "unavailable"; } catch { return "unavailable"; }
}

export function AnalysisReviewPanel({ runId, stateVersion, connectionStatus, workflowEvents, refreshAuthoritativeState }: { runId: string; stateVersion: number; connectionStatus: string; artifacts: ArtifactRefDto[]; workflowEvents: Array<{ event_type: string; sequence: number; payload?: Record<string, unknown> }>; refreshAuthoritativeState?: () => Promise<unknown> }) {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [decision, setDecision] = useState<G04Decision>("approve");
  const [comment, setComment] = useState("");
  const [retryReason, setRetryReason] = useState("Retry the exact failed analysis after correcting the reported failure.");
  const operationKeys = useRef(createLogicalOperationKeys(`analysis-${runId}`));
  const latestEvent = useMemo(() => [...workflowEvents].reverse().find((event) => ANALYSIS_EVENTS.includes(event.event_type)), [workflowEvents]);
  const parityCompleted = workflowEvents.some((event) => event.event_type === "PARITY_BASELINE_COMPLETED");
  const analysisStarted = workflowEvents.some((event) => ANALYSIS_EVENTS.includes(event.event_type));

  const refresh = useCallback(async () => {
    if (!parityCompleted && !analysisStarted) { setLoading(false); setEmpty(true); return; }
    setLoading(true); setError(null);
    try { setAnalysis(await getAnalysis(runId)); setEmpty(false); }
    catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) setEmpty(true);
      else setError(`Analysis could not be loaded. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`);
    } finally { setLoading(false); }
  }, [runId, parityCompleted, analysisStarted]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion, latestEvent?.sequence]);

  async function startAnalysis() {
    const action = "start";
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await generateAnalysis(runId, { expected_state_version: stateVersion, idempotency_key: operationKeys.current.get(action), correlation_id: operationKeys.current.get("start-correlation") });
      operationKeys.current.complete(action); operationKeys.current.complete("start-correlation");
      setAnalysis(result); setEmpty(false); await refreshAuthoritativeState?.();
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) { operationKeys.current.complete(action); operationKeys.current.complete("start-correlation"); setStale(true); await refresh(); }
      else setError(`Analysis generation failed. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`);
    } finally { setWorking(false); }
  }

  async function retryFailedAnalysis() {
    if (!analysis?.analysis_id || !analysis.retryable || !retryReason.trim()) return;
    const action = `retry-${analysis.analysis_id}`;
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await retryAnalysis(runId, { expected_state_version: analysis.state_version, failed_analysis_id: analysis.analysis_id, idempotency_key: operationKeys.current.get(action), reason: retryReason.trim() });
      operationKeys.current.complete(action); setAnalysis(result); setEmpty(false); await refreshAuthoritativeState?.();
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) { operationKeys.current.complete(action); setStale(true); await refresh(); }
      else setError(`Analysis retry failed. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`);
    } finally { setWorking(false); }
  }

  const analysisArtifactIntegrityValid = Boolean(analysis?.artifact_ids.length && analysis.artifact_ids.every((id) => Boolean(analysis.artifact_checksums[id])));
  const canDecideG04 = Boolean(analysis?.package && analysis.package_checksum && analysis.gate_status === "pending" && analysis.state_version === stateVersion && analysisArtifactIntegrityValid);

  async function submitDecision() {
    if (!analysis?.package || !analysis.package_checksum || !canDecideG04) return;
    if (decision === "approve_with_comment" && !comment.trim()) { setError("Add a comment before approving with comment."); return; }
    const action = `g04-${analysis.gate_version}-${decision}`;
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await decideG04(runId, { expected_state_version: analysis.state_version, idempotency_key: operationKeys.current.get(action), gate_version: analysis.gate_version, package_checksum: analysis.package_checksum, workspace_fingerprint: analysis.package.workspace_fingerprint, plan_version: analysis.package.plan_version, decision, comment: comment.trim() || null });
      operationKeys.current.complete(action);
      setAnalysis((current) => current ? { ...current, gate_status: result.status, gate_decision: result.decision, state_version: result.state_version, event_sequence: result.event_sequence } : current);
      await refreshAuthoritativeState?.(); await refresh();
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) { operationKeys.current.complete(action); setStale(true); await refresh(); }
      else setError(`G04 decision failed. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`);
    } finally { setWorking(false); }
  }

  const pkg = analysis?.package;
  const approved = analysis?.gate_status === "approved" || analysis?.gate_status === "approved_with_comment";
  const connectionLabel = connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..." : connectionStatus === "recovering" ? "Refreshing authoritative analysis state..." : analysis?.status ?? "not loaded";
  return <section className={styles.panel} aria-labelledby="analysis-review-title">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S2-F04</p><h2 id="analysis-review-title">AI-assisted analysis and G04 review</h2><p className={styles.note}>Deterministic facts remain separate from the AI interpretation.</p></div><span className={styles.status}>{connectionLabel}</span></div>
    {loading ? <p role="status">Loading authoritative analysis...</p> : null}{error ? <p role="alert">{error}</p> : null}{stale ? <p role="alert">The analysis state is stale. The authoritative snapshot was reloaded; review the current package before retrying.</p> : null}
    {!loading && empty && !parityCompleted ? <p className={styles.note}>Waiting for parity baseline completion.</p> : null}
    {!loading && empty && parityCompleted ? <><p className={styles.note}>No analysis package is available yet.</p><button type="button" onClick={() => void startAnalysis()} disabled={working || analysisStarted}>{working ? "Starting analysis..." : "Start analysis"}</button>{analysisStarted ? <p role="status">Analysis has already been queued; waiting for the authoritative attempt.</p> : null}</> : null}
    {analysis?.status === "failed" || analysis?.status === "blocked" ? <div role="alert"><p>Analysis is {analysis.status}: {analysis.error_code ?? "ANALYSIS_UNAVAILABLE"}. G04 is not presented as reviewed.</p><p>Cause: <code>{analysis.cause_code ?? "unavailable"}</code> · Subtype: <code>{analysis.failure_subtype ?? "unavailable"}</code> · Origin: <code>{analysis.failure_origin ?? "unavailable"}</code> · Phase: <code>{analysis.failure_stage ?? "unknown"}</code> · Technical stage: <code>{analysis.technical_stage ?? "unknown"}</code> · Transport started: <code>{analysis.transport_started == null ? "unavailable" : analysis.transport_started ? "yes" : "no"}</code> · Retryable: <code>{analysis.retryable ? "yes" : "no"}</code></p><p>Proposer invocation: <code>{analysis.proposer_invocation_id ?? "unavailable"}</code> · Reviewer invocation: <code>{analysis.reviewer_invocation_id ?? "unavailable"}</code> · Failed invocation: <code>{analysis.failed_invocation_id ?? "unavailable"}</code></p><p>Provider request ID: <code>{analysis.provider_request_id ?? "unavailable"}</code> · Correlation ID: <code>{analysis.correlation_id ?? "unavailable"}</code></p>{analysis.attempt_history?.length ? <><h3>Attempt history</h3><ol className={styles.list}>{analysis.attempt_history.map((attempt, index) => <li key={`${attempt.analysis_id ?? "attempt"}-${attempt.attempt ?? index}`}><strong>Attempt {attempt.attempt ?? index + 1}</strong> · {attempt.status ?? "unknown"}{attempt.failure_stage ? ` · ${attempt.failure_stage}` : ""}{attempt.cause_code ? ` · ${attempt.cause_code}` : ""}{attempt.correlation_id ? <> · <code>{attempt.correlation_id}</code></> : null}</li>)}</ol></> : null}{analysis.artifact_ids.map((id) => <a key={id} className={styles.actionLink} href={analysis.artifact_links[id] ?? `/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">Diagnostic evidence: {id}</a>)}{analysis.retryable ? <><label htmlFor="analysis-retry-reason">Retry reason</label><textarea id="analysis-retry-reason" value={retryReason} onChange={(event) => setRetryReason(event.target.value)} maxLength={4000} /><button type="button" onClick={() => void retryFailedAnalysis()} disabled={working || !retryReason.trim()}>{working ? "Retrying..." : "Retry analysis"}</button></> : null}</div> : null}
    {analysis?.status === "in_progress" ? <p role="status">Analysis is running. This panel will refresh from the authoritative attempt.</p> : null}
    {pkg ? <><div className={styles.twoColumns}><div className={styles.previewPanel}><h3>Deterministic machine facts</h3><ul className={styles.list}>{pkg.deterministic_input_artifacts.map((artifact) => <li key={artifact.artifact_id}><code>{artifact.artifact_id}</code><code>{artifact.checksum}</code></li>)}</ul><p className={styles.note}>Input checksum: <code>{pkg.narrative.deterministic_input_checksum}</code></p></div><div className={styles.previewPanel}><h3>AI interpretation</h3><p>{pkg.narrative.summary}</p><p><strong>Confidence:</strong> {pkg.narrative.evidence_confidence}</p><p><strong>Recommended next action:</strong> {pkg.narrative.recommended_next_action}</p>{pkg.narrative.risk_groups.length ? <><h4>Risk groups</h4><ul>{pkg.narrative.risk_groups.map((risk, index) => <li key={index}>{String(risk.name ?? JSON.stringify(risk))}</li>)}</ul></> : null}{pkg.narrative.unresolved_questions.length ? <><h4>Unresolved questions</h4><ul>{pkg.narrative.unresolved_questions.map((question) => <li key={question}>{question}</li>)}</ul></> : null}</div></div>
      <div className={styles.previewPanel}><h3>Phase Reviewer</h3><p><strong>Decision:</strong> {pkg.reviewer.decision}</p><p><strong>Confidence:</strong> {pkg.reviewer.confidence}</p><p>Proposer checksum: <code>{pkg.proposer_output_checksum}</code></p><p>Reviewer checksum: <code>{pkg.reviewer_output_checksum}</code></p><p>{pkg.reviewer.notes.join(" ")}</p></div>
      <div className={styles.previewPanel}><h3>Model provenance and usage</h3><p>{pkg.model_provenance.provider} · {pkg.model_provenance.role}</p><p>{pkg.reviewer_provenance.provider} · {pkg.reviewer_provenance.role}</p><pre>{JSON.stringify({ proposer: pkg.usage, reviewer: pkg.reviewer_usage }, null, 2)}</pre></div>
      <div className={styles.previewPanel}><h3>Registered evidence</h3><ul className={styles.list}>{analysis.artifact_ids.map((id) => <li key={id}><a href={analysis.artifact_links[id] ?? `/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a> <code>{analysis.artifact_checksums[id]}</code></li>)}</ul></div>
      <div className={styles.previewPanel}><h3>G04: {analysis.gate_status}</h3>{approved ? <p role="status">G04 was accepted by the authoritative backend. Planning will be projected from the durable planning job.</p> : <><label htmlFor="g04-decision">Decision</label><select id="g04-decision" value={decision} onChange={(event) => setDecision(event.target.value as G04Decision)}>{decisions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><label htmlFor="g04-comment">Review comment</label><textarea id="g04-comment" value={comment} onChange={(event) => setComment(event.target.value)} rows={3} />{!canDecideG04 ? <p className={styles.note}>G04 is disabled until the current package, evidence checksums, gate status, and run state version are authoritative.</p> : null}<button type="button" onClick={() => void submitDecision()} disabled={working || !canDecideG04}>{working ? "Recording decision..." : "Record G04 decision"}</button></>}</div>
    </> : null}
  </section>;
}
