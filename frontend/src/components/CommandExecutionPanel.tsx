"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import { executeApprovedCommand, getCommandArtifactById, getCommandExecution, listCommandExecutions } from "@/api/commands";
import type { CommandArtifactMetadata } from "@/api/commands";
import type { CommandExecutionResponseDto, CommandPolicyValidateResponseDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

const FINAL_STATUSES = new Set(["succeeded", "failed", "timed_out", "cancelled", "interrupted", "rejected"]);

function details(error: unknown) {
  if (!(error instanceof ApiClientError)) return { code: "BACKEND_UNAVAILABLE", message: "The execution service is temporarily unavailable.", correlationId: null, requested: null, current: null };
  try {
    const payload = JSON.parse(error.responseBody ?? "{}") as { error_code?: string; message?: string; correlation_id?: string; details?: { requested_version?: number; current_version?: number } };
    return { code: payload.error_code ?? "BACKEND_UNAVAILABLE", message: payload.message ?? error.message, correlationId: payload.correlation_id ?? null, requested: payload.details?.requested_version ?? null, current: payload.details?.current_version ?? null };
  } catch { return { code: "BACKEND_UNAVAILABLE", message: error.message, correlationId: null, requested: null, current: null }; }
}

function label(status: string) { return status.replaceAll("_", " ").toUpperCase(); }
function timestamp(value: string | null | undefined) { return value ? new Date(value).toLocaleString() : "not supplied"; }

export function CommandExecutionPanel({ runId, stateVersion, authorization, refreshAuthoritativeState }: { runId: string; stateVersion: number; authorization: CommandPolicyValidateResponseDto | null; refreshAuthoritativeState?: () => Promise<unknown> }) {
  const [executions, setExecutions] = useState<CommandExecutionResponseDto[]>([]);
  const [selected, setSelected] = useState<CommandExecutionResponseDto | null>(null);
  const [viewStatus, setViewStatus] = useState<"loading" | "ready" | "unavailable" | "not_found">("loading");
  const [submitStatus, setSubmitStatus] = useState<"idle" | "submitting" | "failed">("idle");
  const [error, setError] = useState<ReturnType<typeof details> | null>(null);
  const [artifactMetadata, setArtifactMetadata] = useState<Record<string, CommandArtifactMetadata["artifact"]>>({});
  const [artifactMetadataStatus, setArtifactMetadataStatus] = useState<"idle" | "loading" | "ready" | "unavailable">("idle");
  const attemptKey = useRef<string | null>(null);

  const reload = useCallback(async () => {
    setViewStatus("loading");
    try { const result = await listCommandExecutions(runId); setExecutions(result.executions); setSelected((current) => current ?? result.executions[0] ?? null); setViewStatus("ready"); }
    catch { setViewStatus("unavailable"); }
  }, [runId]);

  useEffect(() => { void reload(); }, [reload]);

  useEffect(() => { attemptKey.current = null; }, [authorization?.authorization_id, authorization?.expected_state_version, runId]);

  useEffect(() => { if (selected && FINAL_STATUSES.has(selected.status)) attemptKey.current = null; }, [selected]);

  useEffect(() => {
    if (!selected || FINAL_STATUSES.has(selected.status)) return;
    const timer = window.setTimeout(async () => {
      try { const current = await getCommandExecution(runId, selected.execution_id); setSelected(current); setExecutions((items) => items.map((item) => item.execution_id === current.execution_id ? current : item)); }
      catch { /* The next bounded refresh or explicit reload reports availability. */ }
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [runId, selected]);

  useEffect(() => {
    let active = true;
    if (!selected || selected.artifact_ids.length === 0) {
      setArtifactMetadata({});
      setArtifactMetadataStatus("idle");
      return () => { active = false; };
    }
    setArtifactMetadataStatus("loading");
    void Promise.all(selected.artifact_ids.map((artifactId) => getCommandArtifactById(artifactId)))
      .then((items) => {
        if (!active) return;
        setArtifactMetadata(Object.fromEntries(items.map((item) => [item.artifact.artifact_id, item.artifact])));
        setArtifactMetadataStatus("ready");
      })
      .catch(() => { if (active) setArtifactMetadataStatus("unavailable"); });
    return () => { active = false; };
  }, [selected]);

  async function execute() {
    if (!authorization || authorization.decision !== "accepted" || submitStatus === "submitting") return;
    if (typeof window !== "undefined" && !window.confirm("Execute this accepted command? The backend will use the immutable authorization decision.")) return;
    const key = attemptKey.current ?? `command-execution:${runId}:${authorization.authorization_id}:${stateVersion}:${crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
    attemptKey.current = key;
    setSubmitStatus("submitting"); setError(null);
    try {
      const result = await executeApprovedCommand(runId, { authorization_decision_id: authorization.authorization_id, expected_state_version: authorization.expected_state_version, idempotency_key: key, requested_by: "control-tower" });
      setSelected(result); setExecutions((items) => items.some((item) => item.execution_id === result.execution_id) ? items.map((item) => item.execution_id === result.execution_id ? result : item) : [result, ...items]); setSubmitStatus("idle");
    } catch (reason: unknown) {
      const parsed = details(reason); setError(parsed); setSubmitStatus("failed");
      if (parsed.code === "STALE_STATE_VERSION") await refreshAuthoritativeState?.();
    }
  }

  return <section className={styles.panel} aria-label="Command executions">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S3-F02</p><h2>Command executions</h2><p className={styles.note}>Authoritative worker status and finalized evidence.</p></div><strong>{viewStatus}</strong></div>
    {authorization?.decision === "accepted" ? <button type="button" onClick={execute} disabled={submitStatus === "submitting" || authorization.expected_state_version !== stateVersion}>{submitStatus === "submitting" ? "Submitting..." : "Execute command"}</button> : <p className={styles.note}>Execution is available only after an accepted, current authorization decision.</p>}
    {authorization && authorization.expected_state_version !== stateVersion ? <p role="alert">Authorization is stale. Refresh the run and authorize the command again before executing.</p> : null}
    {error ? <div role="alert"><strong>{error.code}</strong><p>{error.message}</p>{error.requested !== null ? <p>Requested version: {error.requested}. Current version: {error.current}.</p> : null}{error.correlationId ? <p>Correlation ID: {error.correlationId}</p> : null}{error.code === "IDEMPOTENCY_KEY_REUSED" ? <p>Start a new logical attempt; the existing idempotency key cannot be reused for changed input.</p> : null}</div> : null}
    {viewStatus === "loading" ? <p role="status">Loading command executions...</p> : null}
    {viewStatus === "unavailable" ? <p role="alert">Execution history is temporarily unavailable. Retry from the run.</p> : null}
    {viewStatus === "ready" && executions.length === 0 ? <p className={styles.note}>No command executions have been recorded.</p> : null}
    {executions.length > 0 ? <ul className={styles.list}>{executions.map((execution) => <li key={execution.execution_id}><button type="button" onClick={() => setSelected(execution)}>{execution.command_id} · {label(execution.status)}</button><code>{execution.execution_id}</code></li>)}</ul> : null}
    {selected ? <article className={styles.previewPanel} aria-label="Command execution detail"><h3>Execution detail</h3><div className={styles.dimensionGrid}><div><span>Execution ID</span><code>{selected.execution_id}</code></div><div><span>Run ID</span><code>{selected.run_id}</code></div><div><span>Status</span><strong>{label(selected.status)}</strong></div><div><span>Exit status</span><code>{selected.exit_code ?? "not supplied"}</code></div><div><span>Command template</span><code>{selected.template_id ?? selected.command_id}{selected.template_version ? ` v${selected.template_version}` : ""}</code></div><div><span>Executable</span><code>{selected.executable ?? "not supplied"}</code></div><div><span>Working directory alias</span><code>{selected.workspace_alias ?? "not supplied"}</code></div><div><span>Safe working directory</span><code>{selected.safe_relative_working_directory ?? "not supplied"}</code></div><div><span>Execution profile</span><code>{selected.execution_profile_id ?? "not supplied"}</code></div><div><span>State version</span><code>{selected.state_version}</code></div><div><span>Correlation ID</span><code>{selected.correlation_id ?? "not supplied"}</code></div><div><span>Created</span><time dateTime={selected.created_at ?? undefined}>{timestamp(selected.created_at)}</time></div><div><span>Started</span><time dateTime={selected.started_at ?? undefined}>{timestamp(selected.started_at)}</time></div><div><span>Completed</span><time dateTime={selected.completed_at ?? undefined}>{timestamp(selected.completed_at)}</time></div><div><span>Duration</span><code>{selected.duration_ms === null ? "not supplied" : `${selected.duration_ms} ms`}</code></div><div><span>Failure</span><code>{selected.failure_code ?? "none"}</code></div></div><div><h4>Exact argv</h4><ol>{(selected.arguments ?? []).map((argument, index) => <li key={`${index}-${argument}`}><code>{argument}</code></li>)}</ol></div>{selected.idempotent_replay ? <p className={styles.note}>Idempotent replay: this is the existing execution, not a new process.</p> : null}<h4>Finalized evidence</h4>{selected.artifact_ids.length === 0 ? <p className={styles.note}>Evidence is not available until the worker finalizes the execution.</p> : artifactMetadataStatus === "loading" ? <p role="status">Loading evidence metadata...</p> : artifactMetadataStatus === "unavailable" ? <p role="alert">Evidence metadata is temporarily unavailable. Artifact links remain available.</p> : <ul className={styles.list}>{selected.artifact_ids.map((artifactId) => { const artifact = artifactMetadata[artifactId]; return <li key={artifactId}><a className={styles.actionLink} href={`/api/v1/artifacts/${encodeURIComponent(artifactId)}`} target="_blank" rel="noreferrer">Open artifact {artifactId}</a>{artifact ? <div><span>{artifact.artifact_type} · {artifact.relative_path}</span><code>SHA-256: {artifact.checksum}</code></div> : null}</li>; })}</ul>}</article> : null}
  </section>;
}
