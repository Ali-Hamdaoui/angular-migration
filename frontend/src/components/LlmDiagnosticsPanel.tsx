"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getLlmActivity, getLlmReadiness, getLlmUsage, invokeLlmSmoke } from "@/api/llm";
import type { LlmActivityResponse, LlmInvocationResponse, LlmReadinessResponse, LlmUsageResponse } from "@/types/llm";
import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import styles from "./ControlTowerShell.module.css";

type Props = {
  runId: string;
  stateVersion: number;
  connectionStatus?: AuthoritativeConnectionStatus | "open" | "reconnecting" | "recovering" | "failed";
  refreshAuthoritativeState?: () => Promise<unknown>;
  workflowEvents?: Array<{ event_type: string }>;
};

function formatCost(value: number) { return `$${value.toFixed(6)}`; }
function formatLabel(value: string) { return value.replaceAll("_", " "); }
function operationKey(runId: string) { return `llm-smoke-${runId}-${Date.now()}`; }
function correlationFrom(error: ApiClientError) { try { return (JSON.parse(error.responseBody ?? '{}') as { correlation_id?: string }).correlation_id ?? null; } catch { return null; } }

function connectionLabel(status: Props["connectionStatus"]) {
  if (status === "open") return "Live authoritative LLM state";
  if (status === "reconnecting") return "Connection lost. Reconnecting...";
  if (status === "recovering") return "Refreshing authoritative LLM state...";
  if (status === "failed") return "Unable to refresh authoritative LLM state";
  return "Connecting to authoritative LLM state...";
}

export function LlmDiagnosticsPanel({ runId, stateVersion, connectionStatus, refreshAuthoritativeState, workflowEvents }: Props) {
  const [readiness, setReadiness] = useState<LlmReadinessResponse | null>(null);
  const [activity, setActivity] = useState<LlmActivityResponse | null>(null);
  const [usage, setUsage] = useState<LlmUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sectionErrors, setSectionErrors] = useState<{ readiness: string | null; activity: string | null; usage: string | null }>({ readiness: null, activity: null, usage: null });
  const [correlationId, setCorrelationId] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  const refreshing = useRef(false);
  const refresh = useCallback(async (force = false) => {
    if (refreshing.current && !force) return;
    refreshing.current = true;
    setLoading(true);
    setError(null);
    setSectionErrors({ readiness: null, activity: null, usage: null });
    const result = await Promise.allSettled([getLlmReadiness(), getLlmActivity(runId), getLlmUsage(runId)]);
    const errors = { readiness: null as string | null, activity: null as string | null, usage: null as string | null };
    result.forEach((item, index) => {
      if (item.status === "fulfilled") {
        if (index === 0) setReadiness(item.value as LlmReadinessResponse);
        if (index === 1) setActivity(item.value as LlmActivityResponse);
        if (index === 2) setUsage(item.value as LlmUsageResponse);
        return;
      }
      const message = item.reason instanceof ApiClientError
        ? "The backend could not load this diagnostics section."
        : "This diagnostics section could not be loaded.";
      if (index === 0) errors.readiness = message;
      if (index === 1) errors.activity = message;
      if (index === 2) errors.usage = message;
      if (item.reason instanceof ApiClientError) {
        if (item.reason.status === 409) setStale(true);
        setCorrelationId(correlationFrom(item.reason));
      }
    });
    setSectionErrors(errors);
    if (Object.values(errors).some(Boolean)) setError(null);
    setLoading(false);
    refreshing.current = false;
  }, [runId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh(); }, 50);
    return () => window.clearTimeout(timer);
  }, [refresh, stateVersion]);

  const latest: LlmInvocationResponse | null = activity?.invocations.at(-1) ?? null;
  const running = latest?.status === "in_progress" || working;
  const budgetStatus = useMemo(() => {
    const events = activity?.invocations ?? [];
    if (workflowEvents?.some((event) => event.event_type === 'LLM_BUDGET_BLOCKED')) return 'blocked';
    if (workflowEvents?.some((event) => event.event_type === 'LLM_BUDGET_WARNING')) return 'warning';
    if (events.some((item) => item.status === "blocked" || item.failure_code === "budget")) return "blocked";
    if (latest?.status === "completed") return "within configured policy";
    return "not evaluated";
  }, [activity, latest, workflowEvents]);

  async function invoke() {
    setWorking(true); setError(null); setStale(false); setCorrelationId(null);
    try {
      const result = await invokeLlmSmoke({ run_id: runId, expected_state_version: stateVersion, idempotency_key: operationKey(runId) });
      setCorrelationId(result.correlation_id ?? result.invocation_id);
      await refreshAuthoritativeState?.();
      await refresh(true);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) { setStale(true); setCorrelationId(correlationFrom(reason)); }
      else if (reason instanceof ApiClientError) { setCorrelationId(correlationFrom(reason)); setError('The governed Azure OpenAI invocation failed. Review the correlation ID and backend evidence.'); }
      else setError("The governed Azure OpenAI invocation failed.");
    } finally {
      setWorking(false);
    }
  }

  return <section className={styles.panel} aria-labelledby="llm-diagnostics-title">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S2-F03</p><h2 id="llm-diagnostics-title">LLM diagnostics and usage</h2><p className={styles.note}>Governed Azure OpenAI smoke invocation with estimated cost from the configured pricing snapshot.</p></div><span className={styles.status}>{readiness?.status ?? "not loaded"}</span></div>
    {connectionStatus ? <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel(connectionStatus)}</div> : null}
    {loading ? <p role="status">Loading LLM diagnostics...</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {sectionErrors.readiness ? <p role="alert">Readiness: {sectionErrors.readiness}</p> : null}
    {sectionErrors.activity ? <p role="alert">Activity: {sectionErrors.activity}</p> : null}
    {sectionErrors.usage ? <p role="alert">Usage: {sectionErrors.usage}</p> : null}
    {(sectionErrors.readiness || sectionErrors.activity || sectionErrors.usage) ? <button type="button" onClick={() => void refresh(true)} disabled={loading}>Retry diagnostics</button> : null}
    {stale ? <p role="alert">The run changed while the invocation was requested. Refresh the authoritative state before retrying.</p> : null}
    {readiness?.status === "blocked" ? <p role="alert">Azure OpenAI is not ready: {readiness.error_code ?? "configuration is incomplete"}.</p> : null}
    {!loading && !sectionErrors.activity && !activity?.invocations.length ? <p className={styles.note}>No governed LLM invocations have been recorded.</p> : null}
    <div className={styles.metadataGrid} aria-label="LLM provenance">
      <div><dt>Provider</dt><dd>{latest?.provider ?? readiness?.provider ?? "unknown"}</dd></div>
      <div><dt>Deployment</dt><dd>{latest?.deployment_alias ?? "unknown"}</dd></div><div><dt>Capability</dt><dd>{latest?.model_capability ?? readiness?.model_capability ?? "unknown"}</dd></div>
      <div><dt>Role</dt><dd>{latest?.role ?? "phase_proposer"}</dd></div>
      <div><dt>Task</dt><dd>{latest?.task_type ?? "smoke_check"}</dd></div>
      <div><dt>Prompt</dt><dd>{latest?.prompt_version ?? "unknown"}</dd></div><div><dt>Schema</dt><dd>{latest?.schema_version ?? "unknown"}</dd></div><div><dt>Pricing</dt><dd>{latest?.pricing_version ?? "unknown"}</dd></div>
       <div><dt>Budget</dt><dd>{budgetStatus}</dd></div><div><dt>Provider status</dt><dd>{latest?.provider_http_status ?? "none"}</dd></div><div><dt>Provider code</dt><dd>{latest?.provider_error_code ?? "none"}</dd></div><div><dt>Provider message</dt><dd>{latest?.sanitized_provider_message ?? "none"}</dd></div><div><dt>Provider request</dt><dd>{latest?.provider_request_id ?? "none"}</dd></div><div><dt>Failure stage</dt><dd>{latest?.failure_stage ?? "none"}</dd></div>
    </div>
    <ul className={styles.metricList} aria-label="LLM usage totals">
      <li><span>Input tokens</span><strong>{(usage?.input_tokens ?? latest?.input_tokens ?? 0).toLocaleString()}</strong></li>
      <li><span>Output tokens</span><strong>{(usage?.output_tokens ?? latest?.output_tokens ?? 0).toLocaleString()}</strong></li>
      <li><span>Total tokens</span><strong>{(usage?.total_tokens ?? latest?.total_tokens ?? 0).toLocaleString()}</strong></li>
      <li><span>Estimated input cost</span><strong>{formatCost(usage?.input_cost_usd ?? latest?.input_cost_usd ?? 0)}</strong></li>
      <li><span>Estimated output cost</span><strong>{formatCost(usage?.output_cost_usd ?? latest?.output_cost_usd ?? 0)}</strong></li>
      <li><span>Estimated total cost</span><strong>{formatCost(usage?.total_cost_usd ?? latest?.total_cost_usd ?? 0)}</strong></li>
    </ul>
    {latest ? <div className={styles.previewPanel}><p className={styles.note}>Status: {formatLabel(latest.status)} · retries: {latest.retries} · latency: {latest.latency_ms ?? "not available"} ms · state version: {latest.state_version} · event sequence: {latest.event_sequence}</p>{latest.failure_code ? <p role="alert">Failure code: {latest.failure_code}</p> : null}<p className={styles.note}>Correlation ID: <code>{latest.correlation_id ?? "none"}</code></p><p className={styles.note}>Artifacts: {latest.artifact_ids.length ? latest.artifact_ids.map((id) => <a key={id} href={latest.artifact_links?.[id] ?? `/api/v1/artifacts/${id}`} target="_blank" rel="noreferrer">{id}</a>) : "none"}</p></div> : null}
    {correlationId ? <p className={styles.note}>Correlation/invocation ID: <code>{correlationId}</code></p> : null}
    <div className={styles.previewHeader}><span className={styles.note}>Evidence is read from the backend snapshot and durable events.</span><button type="button" onClick={() => void invoke()} disabled={working || loading || readiness?.status !== "ready"}>{running ? "Invoking..." : "Run governed smoke check"}</button></div>
  </section>;
}
