"use client";

import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
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
type PipelineStep = { label: string; started: string[]; completed: string[]; failed: string[]; blocked: string[] };
type PipelineStatus = 'pending' | 'running' | 'completed' | 'failed' | 'blocked';
const pipelineSteps: PipelineStep[] = [
  { label: 'Source intake', started: ['SOURCE_INTAKE_QUEUED', 'SOURCE_INTAKE_STARTED'], completed: ['SOURCE_INTAKE_COMPLETED'], failed: ['SOURCE_INTAKE_FAILED'], blocked: [] },
  { label: 'Source snapshot', started: ['SNAPSHOT_STARTED', 'SNAPSHOT_PROGRESS_UPDATED'], completed: ['SNAPSHOT_CREATED'], failed: ['SNAPSHOT_FAILED', 'SNAPSHOT_QUARANTINED'], blocked: [] },
  { label: 'G02 approval', started: ['G02_CREATED'], completed: ['G02_APPROVED'], failed: ['G02_REJECTED'], blocked: ['G02_STALE', 'SOURCE_INTEGRITY_FAILED'] },
  { label: 'Runtime validation', started: ['EXECUTION_PROFILE_RESOLUTION_STARTED'], completed: ['EXECUTION_PROFILE_RESOLVED', 'EXECUTION_PROFILE_SELECTED'], failed: [], blocked: ['EXECUTION_PROFILE_BLOCKED'] },
  { label: 'Baseline preparation', started: ['BASELINE_WORKSPACE_STARTED'], completed: ['BASELINE_WORKSPACE_READY'], failed: [], blocked: ['BASELINE_INSTALL_BLOCKED'] },
  { label: 'Dependency installation', started: ['COMMAND_QUEUED', 'COMMAND_STARTED', 'COMMAND_OUTPUT_CHUNK'], completed: ['BASELINE_INSTALL_SUCCEEDED'], failed: ['BASELINE_INSTALL_FAILED', 'COMMAND_INTERRUPTED', 'COMMAND_CANCELLED'], blocked: [] },
  { label: 'Build', started: ['BASELINE_BUILD_STARTED'], completed: ['BASELINE_BUILD_COMPLETED'], failed: [], blocked: ['BASELINE_BLOCKED'] },
  { label: 'Tests', started: ['BASELINE_TESTS_STARTED'], completed: ['BASELINE_TESTS_COMPLETED'], failed: [], blocked: ['BASELINE_BLOCKED'] },
  { label: 'Lint', started: ['BASELINE_LINT_STARTED'], completed: ['BASELINE_LINT_COMPLETED'], failed: [], blocked: ['BASELINE_BLOCKED'] },
  { label: 'Baseline qualification', started: [], completed: ['BASELINE_QUALIFIED', 'BASELINE_QUALIFIED_WITH_KNOWN_FAILURES'], failed: [], blocked: ['BASELINE_BLOCKED'] },
  { label: 'G03 readiness', started: [], completed: ['G03_CREATED'], failed: [], blocked: [] },
];

function pipelineState(step: PipelineStep, events: AuthoritativeRunStateDto['workflow_events']): { status: PipelineStatus; event?: AuthoritativeRunStateDto['workflow_events'][number] } {
  const relevant = events.filter((event) => [...step.started, ...step.completed, ...step.failed, ...step.blocked].includes(event.event_type));
  const latest = relevant.at(-1);
  if (!latest) return { status: 'pending' };
  if (step.completed.includes(latest.event_type)) return { status: 'completed', event: latest };
  if (step.failed.includes(latest.event_type)) return { status: 'failed', event: latest };
  if (step.blocked.includes(latest.event_type)) return { status: 'blocked', event: latest };
  return { status: 'running', event: latest };
}

export function AuthoritativeRunDashboard({ runId, initialState }: { runId: string; initialState: AuthoritativeRunStateDto }) {
  const { state, status, error, refresh } = useAuthoritativeRun(runId, initialState);
  const connectionLabel = {
    loading: "Loading authoritative state?", connecting: "Connecting to backend events?", open: "Live ? authoritative state", reconnecting: "Connection lost ? reconnecting?", recovering: "Refreshing authoritative snapshot?", failed: "Unable to refresh authoritative state",
  }[status];

  const pipelineStates = pipelineSteps.map((step) => pipelineState(step, state.workflow_events));
  const completedPipelineSteps = pipelineStates.filter((step) => step.status === 'completed').length;
  const activePipelineStep = Math.min(completedPipelineSteps, pipelineSteps.length - 1);

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
        <div className={styles.pipelineHeading}><p className={styles.kicker}>Evolution pipeline</p><span>{completedPipelineSteps} of {pipelineSteps.length} stages complete</span></div>
        <ol className={styles.pipelineList}>{pipelineSteps.map((step, index) => {
          const current = pipelineStates[index];
          const active = current.status === 'running' || (current.status === 'pending' && index === activePipelineStep);
          const className = current.status === 'completed' ? styles.pipelineComplete : current.status === 'failed' ? styles.pipelineFailed : current.status === 'blocked' ? styles.pipelineBlocked : active ? styles.pipelineActive : styles.pipelinePending;
          return <li className={className} key={step.label} aria-label={`${step.label}: ${current.status}`}><span>{current.status === 'completed' ? 'âœ“' : String(index + 1).padStart(2, '0')}</span><strong>{step.label}</strong><small className={styles.pipelineMeta}>{current.status}{current.event ? ` · ${current.event.occurred_at}` : ''}</small></li>;
        })}</ol>
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
        <section className={styles.panel} aria-label="Run evidence"><h2>Run evidence</h2>{state.artifacts.length === 0 ? <p className={styles.note}>No run artifacts are available.</p> : <ul className={styles.list}>{state.artifacts.map((artifact) => <li key={artifact.artifact_id}><code>{artifact.relative_path}</code><span>{artifact.checksum}</span></li>)}</ul>}</section>
      </div>
      </aside>
      </div>
    </main>
  );
}

import { LlmDiagnosticsPanel } from './LlmDiagnosticsPanel';
