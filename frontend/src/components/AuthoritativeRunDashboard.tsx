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
import { CommandPolicyInspector } from "./CommandPolicyInspector";
import { AuthoritativeRunCancellationPanel } from "./AuthoritativeRunCancellationPanel";
import { LlmDiagnosticsPanel } from "./LlmDiagnosticsPanel";
import { ControlTowerHeader } from "./control-tower/ControlTowerHeader";
import { ControlTowerSidebar, type ControlTowerSection } from "./control-tower/ControlTowerSidebar";
import { PipelineSection } from "./control-tower/PipelineSection";
import { WorkflowEventsSection } from "./control-tower/WorkflowEventsSection";
import styles from "./ControlTowerShell.module.css";
import "./control-tower/ControlTowerLayout.module.css";

export function AuthoritativeRunDashboard({ runId, initialState }: { runId: string; initialState: AuthoritativeRunStateDto }) {
  const { state, status, error, refresh } = useAuthoritativeRun(runId, initialState);
  const [activeSection, setActiveSection] = useState<ControlTowerSection>("overview");
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [retryingSourceIntake, setRetryingSourceIntake] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const connectionLabel = { loading: "Loading authoritative state…", connecting: "Connecting to backend events…", open: "Live · authoritative state", reconnecting: "Connection lost · reconnecting…", recovering: "Refreshing authoritative snapshot…", failed: "Unable to refresh authoritative state" }[status];
  const has = (...types: string[]) => state.workflow_events.some((event) => types.includes(event.event_type));
  const baselineAvailable = has("BASELINE_WORKSPACE_STARTED", "BASELINE_WORKSPACE_READY");
  const qualificationAvailable = (has("G02_APPROVED") && has("BASELINE_INSTALL_SUCCEEDED")) || has("BASELINE_BLOCKED", "BASELINE_QUALIFIED", "G03_CREATED", "G03_APPROVED", "G03_REJECTED");
  const qualificationActionRequired = qualificationAvailable && !has("G03_APPROVED");
  const baselineParityAvailable = has("BASELINE_QUALIFIED", "BASELINE_QUALIFIED_WITH_KNOWN_FAILURES", "G03_CREATED", "BASELINE_FAILURES_FINGERPRINTED");
  const available = (title: string) => <div className="controlTowerEmpty">{title} is not available for the current authoritative run state.</div>;
  const heading = (title: string, description: string) => <div className="controlTowerSectionIntro"><div><span className="controlTowerEyebrow">Live projection</span><h2>{title}</h2></div><p>{description}</p></div>;
  async function retrySourceIntake() {
    setRetryingSourceIntake(true); setRetryError(null);
    try { await retryAuthoritativeSourceIntake(runId, { expected_state_version: state.state_version, idempotency_key: `retry-source-intake-${runId}-${state.state_version}`, actor: "control-tower" }); await refresh(); }
    catch { setRetryError("The source-intake retry could not be started. Refresh the authoritative state and inspect the failure evidence."); }
    finally { setRetryingSourceIntake(false); }
  }
  const sourceName = state.source_path.split(/[\\/]/).at(-1) ?? "source";
  const targetName = state.target_output_path.split(/[\\/]/).at(-1) ?? "target";
  const shared = { runId, initialState: state };
  return <main className="controlTowerDashboard">
    <ControlTowerSidebar activeSection={activeSection} open={navigationOpen} onSelect={setActiveSection} onClose={() => setNavigationOpen(false)} />
    <div className="controlTowerMain">
      <ControlTowerHeader runId={state.run_id} status={status} connectionLabel={connectionLabel} onMenu={() => setNavigationOpen(true)} state={state} />
      <div className="controlTowerContent">
        <section className="controlTowerSummary" aria-label="Authoritative run summary"><div><span className="controlTowerEyebrow">Angular migration / live run</span><h1>{sourceName} → {targetName}</h1><p>Run ID <code>{state.run_id}</code></p></div><div className="controlTowerDimensions"><div><span>Live connection</span><strong>{status}</strong></div><div><span>Authoritative status</span><strong>{state.status}</strong></div><div><span>Phase / gate</span><strong>{state.run_phase} · {state.approval_status}</strong></div><div><span>State version</span><strong>{state.state_version}</strong></div></div></section>
        <section hidden={activeSection !== "overview"} className="controlTowerSection" aria-labelledby="overview-navigation-item">{heading("Overview", "The current backend-owned run projection.")}{error ? <section className={styles.panel}><p role="alert">{error}</p></section> : null}<section className={styles.overviewGrid}><section className={styles.panel}><span className={styles.kicker}>Current phase</span><h2>{state.run_phase}</h2><p className={styles.note}>{state.phase_status}</p></section><section className={styles.panel}><span className={styles.kicker}>Run metrics</span><div className={styles.metricGrid}><strong>{state.workflow_events.length}<small>events</small></strong><strong>{state.artifacts.length}<small>artifacts</small></strong><strong>{state.state_version}<small>version</small></strong></div></section></section><section className={styles.panel}><h2>Run context</h2><dl className={styles.metadataGrid}><div><dt>Source</dt><dd><code>{state.source_path}</code></dd></div><div><dt>Target</dt><dd><code>{state.target_output_path}</code></dd></div><div><dt>Updated</dt><dd>{state.updated_at}</dd></div></dl></section><section className={styles.panel}><h2>Recent decision</h2><p className={styles.note}>{state.workflow_events.at(-1)?.event_type ?? "No events have been recorded."}</p></section><details className={styles.dangerZone}><summary>Run controls</summary><AuthoritativeRunCancellationPanel runId={runId} state={state} refresh={refresh} /></details></section>
        <section hidden={activeSection !== "pipeline"} className="controlTowerSection" aria-labelledby="pipeline-navigation-item">{heading("Pipeline", "A compact stage view of the authoritative workflow.")}<PipelineSection state={state} retryError={retryError} retrying={retryingSourceIntake} onRetry={() => void retrySourceIntake()} qualificationAvailable={qualificationAvailable} qualificationActionRequired={qualificationActionRequired}>{() => <BaselineQualificationPanel runId={runId} stateVersion={state.state_version} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />}</PipelineSection><div hidden><SourceSnapshotPanel {...shared} />{has("G02_CREATED", "G02_APPROVED", "G02_REJECTED", "G02_STALE") ? <G02ReviewPanel {...shared} /> : null}{has("EXECUTION_PROFILE_RESOLUTION_STARTED", "EXECUTION_PROFILE_RESOLVED", "EXECUTION_PROFILE_SELECTED", "EXECUTION_PROFILE_BLOCKED") ? <ExecutionProfilePanel {...shared} /> : null}{has("BASELINE_WORKSPACE_STARTED", "BASELINE_WORKSPACE_READY") ? <BaselinePreparationPanel {...shared} /> : null}{baselineAvailable ? <BaselineInstallationPanel {...shared} connectionStatus={status} /> : null}{baselineAvailable ? <BaselineValidationPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} availableKinds={(["build", "test", "lint"] as const)} /> : null}{has("G06_APPROVED", "STAGE_PLAN_CREATED", "EXECUTION_PROFILE_SELECTED", "BASELINE_WORKSPACE_READY") ? <CommandPolicyInspector runId={runId} runState={state} stateVersion={state.state_version} connectionStatus={status} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} /> : null}</div></section>
        <section hidden={activeSection !== "analysis"} className="controlTowerSection" aria-labelledby="analysis-navigation-item">{heading("Analysis & G04", "Reviewer output and the next human decision.")}{has("DISCOVERY_COMPLETED", "ANALYSIS_AGENT_STARTED", "ANALYSIS_AGENT_COMPLETED", "ANALYSIS_AGENT_FAILED", "G04_CREATED") ? <AnalysisReviewPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} /> : available("Analysis")}</section>
        <section hidden={activeSection !== "feasibility"} className="controlTowerSection" aria-labelledby="feasibility-navigation-item">{heading("Feasibility & G05", "Compatibility evidence and feasibility approval.")}{has("G04_APPROVED", "COMPATIBILITY_RESOLUTION_STARTED", "COMPATIBILITY_RESOLUTION_COMPLETED", "COMPATIBILITY_RESOLUTION_BLOCKED", "G05_CREATED") ? <FeasibilityPanel {...shared} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} /> : available("Feasibility")}</section>
        <section hidden={activeSection !== "planning"} className="controlTowerSection" aria-labelledby="planning-navigation-item">{heading("Planning & G06", "Migration plan, review, and approval.")}{has("G05_APPROVED", "MIGRATION_PLAN_CREATED", "STAGE_PLAN_CREATED", "PLAN_REVISION_CREATED", "G06_CREATED") ? <><MigrationPlanPanel {...shared} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} /><PlanReviewPanel {...shared} connectionStatus={status} refreshAuthoritativeState={refresh} /></> : available("Planning")}</section>
        <section hidden={activeSection !== "discovery"} className="controlTowerSection" aria-labelledby="discovery-navigation-item">{heading("Discovery", "Findings captured from the authoritative discovery phase.")}{has("G03_APPROVED", "DISCOVERY_STARTED", "SCANNER_COMPLETED", "DISCOVERY_COMPLETED", "DISCOVERY_BLOCKED") ? <DiscoveryFindingsPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} /> : available("Discovery")}</section>
        <section hidden={activeSection !== "parity"} className="controlTowerSection" aria-labelledby="parity-navigation-item">{heading("Parity", "Baseline and parity evidence.")}{has("PARITY_BASELINE_STARTED", "PARITY_BASELINE_COMPLETED", "PARITY_BASELINE_BLOCKED") || baselineParityAvailable ? <>{has("PARITY_BASELINE_STARTED", "PARITY_BASELINE_COMPLETED", "PARITY_BASELINE_BLOCKED") ? <ParityBaselinePanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} /> : null}{baselineParityAvailable ? <BaselineParityPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} workflowEvents={state.workflow_events} /> : null}</> : available("Parity")}</section>
        <section hidden={activeSection !== "evidence"} className="controlTowerSection" aria-labelledby="evidence-navigation-item">{heading("Files & Artifacts", "Immutable evidence registered by the backend.")}<section className={styles.panel} aria-label="Run evidence">{state.artifacts.length === 0 ? <p className={styles.note}>No run artifacts are available.</p> : <ul className={styles.list}>{state.artifacts.map((artifact) => <li key={artifact.artifact_id}><a className={styles.actionLink} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`} target="_blank" rel="noreferrer"><code>{artifact.relative_path}</code></a><span>{artifact.checksum}</span></li>)}</ul>}</section></section>
        <section hidden={activeSection !== "llm"} className="controlTowerSection" aria-labelledby="llm-navigation-item">{heading("LLM Diagnostics", "Provider activity and usage projected from the run.")}<LlmDiagnosticsPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} refreshAuthoritativeState={refresh} workflowEvents={state.workflow_events} /></section>
        <section hidden={activeSection !== "events"} className="controlTowerSection" aria-labelledby="events-navigation-item">{heading("Workflow Events", "Searchable ordered history from the authoritative stream.")}<WorkflowEventsSection events={state.workflow_events} /></section>
      </div>
    </div>
  </main>;
}
