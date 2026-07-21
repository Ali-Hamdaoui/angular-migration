"use client";

import { useState } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
import { retryAuthoritativeSourceIntake } from "@/api/runs";
import { getBackendBaseUrl } from "@/api/client";
import { SourceSnapshotPanel } from "./SourceSnapshotPanel";
import { G02ReviewPanel } from "./G02ReviewPanel";
import { ExecutionProfilePanel } from "./ExecutionProfilePanel";
import { BaselinePreparationPanel } from "./BaselinePreparationPanel";
import { BaselineInstallationPanel } from "./BaselineInstallationPanel";
import { BaselineParityPanel } from "./BaselineParityPanel";
import { BaselineValidationPanel } from "./BaselineValidationPanel";
import { BaselineQualificationPanel } from "./BaselineQualificationPanel";
import { DiscoveryFindingsPanel } from "./DiscoveryFindingsPanel";
import { ParityBaselinePanel } from "./ParityBaselinePanel";
import { AnalysisReviewPanel } from "./AnalysisReviewPanel";
import { FeasibilityPanel } from "./FeasibilityPanel";
import { MigrationPlanPanel } from "./MigrationPlanPanel";
import { PlanReviewPanel } from "./PlanReviewPanel";
import styles from "./ControlTowerShell.module.css";

import { CommandPolicyInspector } from "./CommandPolicyInspector";
import { AuthoritativeRunCancellationPanel } from "./AuthoritativeRunCancellationPanel";
type PipelineStep = { label: string; started: string[]; completed: string[]; failed: string[]; blocked: string[]; kind?: string };
type PipelineStatus = 'pending' | 'running' | 'completed' | 'failed' | 'blocked';
const pipelineSteps: PipelineStep[] = [
  { label: 'Source intake', started: ['SOURCE_INTAKE_QUEUED', 'SOURCE_INTAKE_STARTED'], completed: ['SOURCE_INTAKE_COMPLETED'], failed: ['SOURCE_INTAKE_FAILED'], blocked: [] },
  { label: 'Source snapshot', started: ['SNAPSHOT_STARTED', 'SNAPSHOT_PROGRESS_UPDATED'], completed: ['SNAPSHOT_CREATED'], failed: ['SNAPSHOT_FAILED', 'SNAPSHOT_QUARANTINED'], blocked: [] },
  { label: 'G02 approval', started: ['G02_CREATED'], completed: ['G02_APPROVED'], failed: ['G02_REJECTED'], blocked: ['G02_STALE', 'SOURCE_INTEGRITY_FAILED'] },
  { label: 'Runtime validation', started: ['EXECUTION_PROFILE_RESOLUTION_STARTED'], completed: ['EXECUTION_PROFILE_RESOLVED', 'EXECUTION_PROFILE_SELECTED'], failed: [], blocked: ['EXECUTION_PROFILE_BLOCKED'] },
  { label: 'Baseline preparation', started: ['BASELINE_WORKSPACE_STARTED'], completed: ['BASELINE_WORKSPACE_READY'], failed: [], blocked: ['BASELINE_INSTALL_BLOCKED'] },
  { label: 'Dependency installation', started: ['COMMAND_QUEUED', 'COMMAND_STARTED', 'COMMAND_OUTPUT_CHUNK'], completed: ['BASELINE_INSTALL_SUCCEEDED'], failed: ['BASELINE_INSTALL_FAILED', 'COMMAND_INTERRUPTED', 'COMMAND_CANCELLED'], blocked: [] },
  { label: 'Build', started: ['BASELINE_BUILD_STARTED', 'COMMAND_OUTPUT_CHUNK'], completed: ['BASELINE_BUILD_COMPLETED'], failed: [], blocked: ['BASELINE_BLOCKED'], kind: 'build' },
  { label: 'Tests', started: ['BASELINE_TESTS_STARTED', 'COMMAND_OUTPUT_CHUNK'], completed: ['BASELINE_TESTS_COMPLETED'], failed: [], blocked: ['BASELINE_BLOCKED'], kind: 'test' },
  { label: 'Lint', started: ['BASELINE_LINT_STARTED', 'COMMAND_OUTPUT_CHUNK'], completed: ['BASELINE_LINT_COMPLETED'], failed: [], blocked: ['BASELINE_BLOCKED'], kind: 'lint' },
  { label: 'Baseline qualification', started: [], completed: ['BASELINE_QUALIFIED', 'BASELINE_QUALIFIED_WITH_KNOWN_FAILURES'], failed: [], blocked: ['BASELINE_BLOCKED'] },
  { label: 'G03 readiness', started: [], completed: ['G03_CREATED'], failed: [], blocked: [] },
];

function isStepEvent(step: PipelineStep, event: AuthoritativeRunStateDto['workflow_events'][number]) {
  if (![...step.started, ...step.completed, ...step.failed, ...step.blocked].includes(event.event_type)) return false;
  return event.event_type !== 'COMMAND_OUTPUT_CHUNK' || !step.kind || event.payload.kind === step.kind;
}

function pipelineState(step: PipelineStep, events: AuthoritativeRunStateDto['workflow_events']): { status: PipelineStatus; event?: AuthoritativeRunStateDto['workflow_events'][number] } {
  const relevant = events.filter((event) => isStepEvent(step, event)).sort((a, b) => a.sequence - b.sequence);
  const latest = relevant.at(-1);
  if (!latest) return { status: 'pending' };
  if (step.completed.includes(latest.event_type)) return { status: 'completed', event: latest };
  if (step.failed.includes(latest.event_type)) return { status: 'failed', event: latest };
  if (step.blocked.includes(latest.event_type)) return { status: 'blocked', event: latest };
  return { status: 'running', event: latest };
}

function stepEvents(step: PipelineStep, events: AuthoritativeRunStateDto['workflow_events']) {
  return events.filter((event) => isStepEvent(step, event)).sort((a, b) => a.sequence - b.sequence);
}

function payloadValue(event: AuthoritativeRunStateDto['workflow_events'][number] | undefined, keys: string[]): string | null {
  for (const key of keys) {
    const value = event?.payload[key];
    if (typeof value === 'string' && value.length > 0) return value;
    if (typeof value === 'number') return String(value);
  }
  return null;
}

function commandText(event: AuthoritativeRunStateDto['workflow_events'][number] | undefined): string | null {
  const command = event?.payload.command;
  if (typeof command === 'string') return command;
  const executable = event?.payload.executable;
  const argumentsValue = event?.payload.arguments;
  if (typeof executable === 'string' && Array.isArray(argumentsValue) && argumentsValue.every((item) => typeof item === 'string')) {
    return [executable, ...argumentsValue].join(' ');
  }
  return null;
}

function eventArtifactIds(event: AuthoritativeRunStateDto['workflow_events'][number] | undefined): string[] {
  const values = [event?.payload.artifact_id, event?.payload.stdout_artifact_id, event?.payload.stderr_artifact_id, event?.payload.result_artifact_id, event?.payload.artifact_ids, event?.payload.evidence_artifact_ids];
  return [...new Set(values.flatMap((value) => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : typeof value === 'string' ? [value] : []))];
}

function PipelineStepDetail({ step, current, events }: { step: PipelineStep; current: ReturnType<typeof pipelineState>; events: AuthoritativeRunStateDto['workflow_events'] }) {
  if (!current.event) return null;
  const history = stepEvents(step, events);
  const terminal = history.find((event) => step.completed.includes(event.event_type) || step.failed.includes(event.event_type) || step.blocked.includes(event.event_type));
  const message = payloadValue(current.event, ['message', 'reason', 'error_message', 'blocker']);
  const command = commandText(current.event);
  const exitCode = payloadValue(current.event, ['exit_code']);
  const liveOutput = typeof current.event.payload.chunk === 'string' ? current.event.payload.chunk : null;
  const artifactIds = eventArtifactIds(current.event);
  return <div className={styles.previewPanel}><strong>{step.label}</strong><small>Started: {history[0]?.occurred_at ?? 'not recorded'}{terminal ? ` · Finished: ${terminal.occurred_at}` : ''}</small>{message ? <p>{message}</p> : null}{command ? <p>Command: <code>{command}</code></p> : null}{exitCode ? <p>Exit code: <code>{exitCode}</code></p> : null}{liveOutput ? <pre aria-label={`${step.label} live output`}>{liveOutput}</pre> : null}{artifactIds.length ? <p>Evidence: {artifactIds.map((id) => <a className={styles.actionLink} key={id} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a>)}</p> : null}</div>;
}

export function AuthoritativeRunDashboard({ runId, initialState }: { runId: string; initialState: AuthoritativeRunStateDto }) {
  const { state, status, error, refresh } = useAuthoritativeRun(runId, initialState);
  const [retryingSourceIntake, setRetryingSourceIntake] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const connectionLabel = {
    loading: "Loading authoritative state?", connecting: "Connecting to backend events?", open: "Live ? authoritative state", reconnecting: "Connection lost ? reconnecting?", recovering: "Refreshing authoritative snapshot?", failed: "Unable to refresh authoritative state",
  }[status];

  const baselineEvidenceReady = state.workflow_events.some((event) => event.event_type === 'BASELINE_QUALIFIED' || event.event_type === 'BASELINE_QUALIFIED_WITH_KNOWN_FAILURES' || event.event_type === 'G03_CREATED');
  const visiblePipelineSteps = baselineEvidenceReady ? pipelineSteps : pipelineSteps.filter((step) => step.label !== 'G03 readiness');
  const pipelineStates = visiblePipelineSteps.map((step) => pipelineState(step, state.workflow_events));
  const completedPipelineSteps = pipelineStates.filter((step) => step.status === 'completed').length;
  const activePipelineStep = Math.min(completedPipelineSteps, visiblePipelineSteps.length - 1);

  async function retrySourceIntake() {
    setRetryingSourceIntake(true); setRetryError(null);
    try {
      await retryAuthoritativeSourceIntake(runId, { expected_state_version: state.state_version, idempotency_key: `retry-source-intake-${runId}-${state.state_version}`, actor: "control-tower" });
      await refresh();
    } catch {
      setRetryError("The source-intake retry could not be started. Refresh the authoritative state and inspect the failure evidence.");
    } finally { setRetryingSourceIntake(false); }
  }

  return (
    <main className={styles.shell}>
      <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>
      <header className={styles.header}>
        <div><p className={styles.kicker}>Authoritative migration run</p><h1>{state.source_path} ? {state.target_output_path}</h1><p>{state.run_id}</p></div>
        <div className={styles.dimensionGrid} aria-label="Authoritative run dimensions">
          <div><span>Run</span><strong>{state.status}</strong></div><div><span>Phase</span><strong>{state.run_phase}</strong></div>
          <div><span>Approval</span><strong>{state.approval_status}</strong></div><div><span>Version</span><strong>{state.state_version}</strong></div>
        </div>
      </header>
      <section className={styles.pipeline} aria-label={'Migration workflow progress'}>
        <div className={styles.pipelineHeading}><p className={styles.kicker}>Evolution pipeline</p><span>{completedPipelineSteps} of {visiblePipelineSteps.length} stages complete</span></div>
        {retryError ? <p role="alert">{retryError}</p> : null}
        <ol className={styles.pipelineList}>{visiblePipelineSteps.map((step, index) => {
          const current = pipelineStates[index];
          const active = current.status === 'running' || (current.status === 'pending' && index === activePipelineStep);
          const className = current.status === 'completed' ? styles.pipelineComplete : current.status === 'failed' ? styles.pipelineFailed : current.status === 'blocked' ? styles.pipelineBlocked : active ? styles.pipelineActive : styles.pipelinePending;
          return <li className={className} key={step.label} aria-label={`${step.label}: ${current.status}`}><span>{current.status === 'completed' ? 'âœ“' : String(index + 1).padStart(2, '0')}</span><strong>{step.label}</strong><small className={styles.pipelineMeta}>{current.status}{current.event ? ` · ${current.event.occurred_at}` : ''}</small>{index === 0 && current.status === 'failed' ? <button type="button" onClick={() => void retrySourceIntake()} disabled={retryingSourceIntake}>{retryingSourceIntake ? 'Retrying…' : 'Retry source intake'}</button> : null}</li>;
        })}</ol>
        <div aria-label="Pipeline evidence details">{visiblePipelineSteps.map((step, index) => <PipelineStepDetail key={`detail-${step.label}`} step={step} current={pipelineStates[index]} events={state.workflow_events} />)}</div>
      </section>
      {error ? <section className={styles.panel}><p role="alert">{error}</p></section> : null}
      <LlmDiagnosticsPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} refreshAuthoritativeState={refresh} workflowEvents={state.workflow_events} />
      <AnalysisReviewPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />
      <FeasibilityPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />
      <MigrationPlanPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />
      <PlanReviewPanel runId={runId} initialState={state} connectionStatus={status} refreshAuthoritativeState={refresh} />
      <DiscoveryFindingsPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} />
      <ParityBaselinePanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} />
      <div className={styles.dashboardGrid}>
      <div className={styles.primaryColumn}>
      <SourceSnapshotPanel runId={runId} initialState={state} />
      <G02ReviewPanel runId={runId} initialState={state} />
      <ExecutionProfilePanel runId={runId} initialState={state} />
      <BaselinePreparationPanel runId={runId} initialState={state} />
      <BaselineInstallationPanel runId={runId} initialState={state} connectionStatus={status} />
      <BaselineValidationPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} />
      <BaselineQualificationPanel runId={runId} stateVersion={state.state_version} workflowEvents={state.workflow_events} />
      <BaselineParityPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} />
      <CommandPolicyInspector runId={runId} runState={state} stateVersion={state.state_version} connectionStatus={status} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />
      </div>
      <aside className={styles.secondaryColumn}>
      <AuthoritativeRunCancellationPanel runId={runId} state={state} refresh={refresh} />
      <div className={styles.twoColumns}>
        <section className={styles.panel} aria-label="Authoritative workflow events"><h2>Workflow events</h2>{state.workflow_events.length === 0 ? <p className={styles.note}>No events have been recorded.</p> : <ol className={styles.eventList}>{state.workflow_events.map((event) => <li className={styles.eventItem} key={event.event_id}><code className={styles.eventType}>{event.event_type}</code><span className={styles.eventTime}>#{event.sequence} ? {event.occurred_at}</span></li>)}</ol>}</section>
        <section className={styles.panel} aria-label="Run evidence"><h2>Run evidence</h2>{state.artifacts.length === 0 ? <p className={styles.note}>No run artifacts are available.</p> : <ul className={styles.list}>{state.artifacts.map((artifact) => <li key={artifact.artifact_id}><a className={styles.actionLink} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`} target="_blank" rel="noreferrer"><code>{artifact.relative_path}</code></a><span>{artifact.checksum}</span></li>)}</ul>}</section>
      </div>
      </aside>
      </div>
    </main>
  );
}

import { LlmDiagnosticsPanel } from './LlmDiagnosticsPanel';
