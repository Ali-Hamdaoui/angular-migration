"use client";

import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
import { SourceSnapshotPanel } from "./SourceSnapshotPanel";
import { G02ReviewPanel } from "./G02ReviewPanel";
import { ExecutionProfilePanel } from "./ExecutionProfilePanel";
import { BaselinePreparationPanel } from "./BaselinePreparationPanel";
import { BaselineInstallationPanel } from "./BaselineInstallationPanel";
import { BaselineParityPanel } from "./BaselineParityPanel";
import { DiscoveryFindingsPanel } from "./DiscoveryFindingsPanel";
import { ParityBaselinePanel } from "./ParityBaselinePanel";
import { AnalysisReviewPanel } from "./AnalysisReviewPanel";
import styles from "./ControlTowerShell.module.css";

const pipelineSteps = [
  { label: 'Preflight', completeWhen: (events: AuthoritativeRunStateDto['workflow_events']) => events.some((event) => event.event_type.includes('PREFLIGHT')) },
  { label: 'Snapshot', completeWhen: (events: AuthoritativeRunStateDto['workflow_events']) => events.some((event) => event.event_type === 'SNAPSHOT_CREATED') },
  { label: 'Integrity', completeWhen: (events: AuthoritativeRunStateDto['workflow_events']) => events.some((event) => event.event_type === 'G02_APPROVED') },
  { label: 'Baseline', completeWhen: (events: AuthoritativeRunStateDto['workflow_events']) => events.some((event) => event.event_type.startsWith('BASELINE_') && !event.event_type.endsWith('FAILED')) },
  { label: 'Verify', completeWhen: (events: AuthoritativeRunStateDto['workflow_events']) => events.some((event) => event.event_type.includes('VALIDATION') && event.event_type.endsWith('COMPLETED')) },
];

export function AuthoritativeRunDashboard({ runId, initialState }: { runId: string; initialState: AuthoritativeRunStateDto }) {
  const { state, status, error, refresh } = useAuthoritativeRun(runId, initialState);
  const connectionLabel = {
    loading: "Loading authoritative state?", connecting: "Connecting to backend events?", open: "Live ? authoritative state", reconnecting: "Connection lost ? reconnecting?", recovering: "Refreshing authoritative snapshot?", failed: "Unable to refresh authoritative state",
  }[status];

  const completedPipelineSteps = pipelineSteps.filter((step) => step.completeWhen(state.workflow_events)).length;
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
          const completed = step.completeWhen(state.workflow_events);
          const active = !completed && index === activePipelineStep;
          return <li className={completed ? styles.pipelineComplete : active ? styles.pipelineActive : styles.pipelinePending} key={step.label}><span>{completed ? 'âœ“' : String(index + 1).padStart(2, '0')}</span><strong>{step.label}</strong></li>;
        })}</ol>
      </section>
      {error ? <section className={styles.panel}><p role="alert">{error}</p></section> : null}
      <LlmDiagnosticsPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} refreshAuthoritativeState={refresh} workflowEvents={state.workflow_events} />
      <AnalysisReviewPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />
      <DiscoveryFindingsPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} />
      <ParityBaselinePanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} />
      <div className={styles.dashboardGrid}>
      <div className={styles.primaryColumn}>
      <SourceSnapshotPanel runId={runId} initialState={state} />
      <G02ReviewPanel runId={runId} initialState={state} />
      <ExecutionProfilePanel runId={runId} initialState={state} />
      <BaselinePreparationPanel runId={runId} initialState={state} />
      <BaselineInstallationPanel runId={runId} initialState={state} connectionStatus={status} />
      <BaselineParityPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} />
      </div>
      <aside className={styles.secondaryColumn}>
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
