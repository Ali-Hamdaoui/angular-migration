"use client";

import type { AuthoritativeRunStateDto, CommandExecutionResponseDto } from "@/types/generated/api";
import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import type { TransformationProjection } from "@/types/transformation";
import { presentStatus } from "@/presentation/status";
import { getBackendBaseUrl } from "@/api/client";
import { LlmDiagnosticsPanel } from "../LlmDiagnosticsPanel";
import { WorkflowEventsSection } from "./WorkflowEventsSection";
import styles from "./DiagnosticsWorkspace.module.css";

type Props = {
  run: AuthoritativeRunStateDto;
  runId: string;
  connectionStatus: AuthoritativeConnectionStatus;
  connectionError: string | null;
  transformation: TransformationProjection | null;
  transformationStatus: "disabled" | "loading" | "ready" | "empty" | "failed";
  executions: CommandExecutionResponseDto[];
  executionStatus: "idle" | "loading" | "ready" | "unavailable";
  refreshTransformation: () => Promise<void>;
  refreshAuthoritativeState: () => Promise<void>;
};

const CONNECTION_LABELS: Record<AuthoritativeConnectionStatus, string> = {
  loading: "Loading authoritative snapshot",
  connecting: "Connecting to backend events",
  open: "Live · authoritative state",
  reconnecting: "Connection lost · reconnecting",
  recovering: "Refreshing authoritative snapshot",
  failed: "Unable to refresh authoritative state",
};

function blocker(run: AuthoritativeRunStateDto, transformation: TransformationProjection | null): { title: string; summary: string } | null {
  const error = transformation?.active_error;
  if (error) return { title: presentStatus(error.code).label, summary: error.message };
  const failed = [...run.workflow_events].reverse().find((event) => /FAIL|BLOCKED|REJECTED/.test(event.event_type));
  if (!failed) return null;
  return {
    title: presentStatus(failed.event_type).label,
    summary: typeof failed.payload.message === "string" ? failed.payload.message : "The authoritative workflow reported an issue.",
  };
}

function commandLabel(execution: CommandExecutionResponseDto) {
  return [execution.executable, ...(execution.arguments ?? [])].filter(Boolean).join(" ") || execution.command_id;
}

export function DiagnosticsWorkspace({
  run,
  runId,
  connectionStatus,
  connectionError,
  transformation,
  transformationStatus,
  executions,
  executionStatus,
  refreshTransformation,
  refreshAuthoritativeState,
}: Props) {
  const currentBlocker = blocker(run, transformation);
  const canRefresh = connectionStatus === "open";
  async function refresh() {
    if (!canRefresh) return;
    await Promise.allSettled([refreshAuthoritativeState(), refreshTransformation()]);
  }

  return <section className={styles.workspace} aria-labelledby="diagnostics-workspace-title">
    <div className={styles.header}>
      <div><p className={styles.kicker}>Run diagnostics</p><h2 id="diagnostics-workspace-title">Diagnostics</h2><p className={styles.note}>A clear view of blockers, commands, durable events, and governed provider activity.</p></div>
      <button type="button" onClick={() => void refresh()} disabled={!canRefresh} aria-label="Refresh diagnostics">Refresh diagnostics</button>
    </div>
    <div className={styles.connection} role="status" aria-live="polite">{CONNECTION_LABELS[connectionStatus]}{connectionError ? <span> · {connectionError}</span> : null}</div>

    <section className={styles.card} aria-labelledby="diagnostics-summary-title">
      <h3 id="diagnostics-summary-title">Summary</h3>
      <dl className={styles.summaryGrid}><div><dt>Run status</dt><dd>{presentStatus(run.status).label}</dd></div><div><dt>Workflow phase</dt><dd>{presentStatus(run.run_phase).label}</dd></div><div><dt>State version</dt><dd>{run.state_version}</dd></div><div><dt>Events recorded</dt><dd>{run.workflow_events.length}</dd></div></dl>
    </section>

    <section className={styles.card} aria-label="Current blocker">
      <h3 id="diagnostics-blocker-title">Blocker</h3>
      {currentBlocker ? <p role="alert"><strong>{currentBlocker.title}</strong><br />{currentBlocker.summary}</p> : <p className={styles.note}>Not available — no active blocker is recorded.</p>}
    </section>

    <section className={styles.card} aria-label="Commands and logs" aria-labelledby="diagnostics-commands-title">
      <h3 id="diagnostics-commands-title">Commands and logs</h3>
      {executionStatus === "loading" ? <p role="status">Loading command executions…</p> : null}
      {executions.length ? <ol className={styles.commandList}>{executions.map((execution) => <li key={execution.execution_id}><div><strong>{commandLabel(execution)}</strong><span>{presentStatus(execution.status).label}</span></div><p>{execution.failure_reason ?? (execution.exit_code == null ? "No exit code recorded." : `Exit code ${execution.exit_code}`)}</p>{execution.command_log_artifact_id || execution.stdout_artifact_id || execution.stderr_artifact_id ? <a href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(execution.command_log_artifact_id ?? execution.stdout_artifact_id ?? execution.stderr_artifact_id ?? "")}`} target="_blank" rel="noreferrer">Open command log</a> : <span className={styles.note}>Log artifact not available</span>}</li>)}</ol> : <p className={styles.note}>Not available — no command executions are recorded.</p>}
      {executionStatus === "unavailable" ? <p className={styles.note}>Command execution details are not available from the backend.</p> : null}
    </section>

    <WorkflowEventsSection events={run.workflow_events} />

    <section className={styles.card} aria-label="LLM activity" aria-labelledby="diagnostics-llm-title">
      <LlmDiagnosticsPanel runId={runId} stateVersion={run.state_version} connectionStatus={connectionStatus} refreshAuthoritativeState={refreshAuthoritativeState} workflowEvents={run.workflow_events} />
    </section>

    <details className={styles.card}><summary>Raw state</summary><pre className={styles.rawState}>{JSON.stringify(run, null, 2)}</pre><p className={styles.note}>Raw provider payloads and backend identifiers remain available only in their technical disclosures.</p></details>
    {transformationStatus === "failed" ? <p className={styles.note}>Transformation diagnostics are not available from the backend.</p> : null}
  </section>;
}
