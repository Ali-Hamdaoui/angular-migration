"use client";

import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
import { SourceSnapshotPanel } from "./SourceSnapshotPanel";
import styles from "./ControlTowerShell.module.css";

export function AuthoritativeRunDashboard({ runId, initialState }: { runId: string; initialState: AuthoritativeRunStateDto }) {
  const { state, status, error } = useAuthoritativeRun(runId, initialState);
  const connectionLabel = {
    loading: "Loading authoritative state?", connecting: "Connecting to backend events?", open: "Live ? authoritative state", reconnecting: "Connection lost ? reconnecting?", recovering: "Refreshing authoritative snapshot?", failed: "Unable to refresh authoritative state",
  }[status];

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
      {error ? <section className={styles.panel}><p role="alert">{error}</p></section> : null}
      <SourceSnapshotPanel runId={runId} initialState={state} />
      <div className={styles.twoColumns}>
        <section className={styles.panel} aria-label="Authoritative workflow events"><h2>Workflow events</h2>{state.workflow_events.length === 0 ? <p className={styles.note}>No events have been recorded.</p> : <ol className={styles.eventList}>{state.workflow_events.map((event) => <li className={styles.eventItem} key={event.event_id}><code className={styles.eventType}>{event.event_type}</code><span className={styles.eventTime}>#{event.sequence} ? {event.occurred_at}</span></li>)}</ol>}</section>
        <section className={styles.panel} aria-label="Run evidence"><h2>Run evidence</h2>{state.artifacts.length === 0 ? <p className={styles.note}>No run artifacts are available.</p> : <ul className={styles.list}>{state.artifacts.map((artifact) => <li key={artifact.artifact_id}><code>{artifact.relative_path}</code><span>{artifact.checksum}</span></li>)}</ul>}</section>
      </div>
    </main>
  );
}
