"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { getBackendBaseUrl } from "@/api/client";
import { PIPELINE_LABELS } from "@/content/uiCopy";
import styles from "./ControlTowerLayout.module.css";

type Event = AuthoritativeRunStateDto["workflow_events"][number];

export type PipelineStepId =
  | "source-intake"
  | "source-snapshot"
  | "source-approval"
  | "runtime-validation"
  | "baseline-preparation"
  | "dependency-installation"
  | "baseline-build"
  | "baseline-tests"
  | "baseline-lint"
  | "baseline-qualification"
  | "baseline-approval";

type Step = {
  id: PipelineStepId;
  label: string;
  gate?: string;
  started: string[];
  completed: string[];
  failed: string[];
  blocked: string[];
  kind?: string;
};
type PipelineStatus = "pending" | "running" | "action required" | "completed" | "failed" | "blocked";

const steps: Step[] = [
  { id: "source-intake", label: PIPELINE_LABELS["source-intake"], started: ["SOURCE_INTAKE_QUEUED", "SOURCE_INTAKE_STARTED"], completed: ["SOURCE_INTAKE_COMPLETED"], failed: ["SOURCE_INTAKE_FAILED"], blocked: [] },
  { id: "source-snapshot", label: PIPELINE_LABELS["source-snapshot"], started: ["SNAPSHOT_STARTED", "SNAPSHOT_PROGRESS_UPDATED"], completed: ["SNAPSHOT_CREATED"], failed: ["SNAPSHOT_FAILED", "SNAPSHOT_QUARANTINED"], blocked: [] },
  { id: "source-approval", label: PIPELINE_LABELS["source-approval"], gate: "G02", started: ["G02_CREATED"], completed: ["G02_APPROVED"], failed: ["G02_REJECTED"], blocked: ["G02_STALE", "SOURCE_INTEGRITY_FAILED"] },
  { id: "runtime-validation", label: PIPELINE_LABELS["runtime-validation"], started: ["EXECUTION_PROFILE_RESOLUTION_STARTED"], completed: ["EXECUTION_PROFILE_RESOLVED", "EXECUTION_PROFILE_SELECTED"], failed: [], blocked: ["EXECUTION_PROFILE_BLOCKED"] },
  { id: "baseline-preparation", label: PIPELINE_LABELS["baseline-preparation"], started: ["BASELINE_WORKSPACE_STARTED"], completed: ["BASELINE_WORKSPACE_READY"], failed: [], blocked: ["BASELINE_INSTALL_BLOCKED"] },
  { id: "dependency-installation", label: PIPELINE_LABELS["dependency-installation"], started: ["COMMAND_QUEUED", "COMMAND_STARTED", "COMMAND_OUTPUT_CHUNK"], completed: ["BASELINE_INSTALL_SUCCEEDED"], failed: ["BASELINE_INSTALL_FAILED", "COMMAND_INTERRUPTED", "COMMAND_CANCELLED"], blocked: [] },
  { id: "baseline-build", label: PIPELINE_LABELS["baseline-build"], started: ["BASELINE_BUILD_STARTED", "COMMAND_OUTPUT_CHUNK"], completed: ["BASELINE_BUILD_COMPLETED"], failed: [], blocked: [], kind: "build" },
  { id: "baseline-tests", label: PIPELINE_LABELS["baseline-tests"], started: ["BASELINE_TESTS_STARTED", "COMMAND_OUTPUT_CHUNK"], completed: ["BASELINE_TESTS_COMPLETED"], failed: [], blocked: [], kind: "test" },
  { id: "baseline-lint", label: PIPELINE_LABELS["baseline-lint"], started: ["BASELINE_LINT_STARTED", "COMMAND_OUTPUT_CHUNK"], completed: ["BASELINE_LINT_COMPLETED"], failed: [], blocked: [], kind: "lint" },
  { id: "baseline-qualification", label: PIPELINE_LABELS["baseline-qualification"], started: [], completed: ["BASELINE_QUALIFIED", "BASELINE_QUALIFIED_WITH_KNOWN_FAILURES"], failed: [], blocked: ["BASELINE_BLOCKED"] },
  { id: "baseline-approval", label: PIPELINE_LABELS["baseline-approval"], gate: "G03", started: [], completed: ["G03_CREATED"], failed: [], blocked: [] },
];

function relevant(step: Step, event: Event) { return [...step.started, ...step.completed, ...step.failed, ...step.blocked].includes(event.event_type) && (event.event_type !== "COMMAND_OUTPUT_CHUNK" || !step.kind || event.payload.kind === step.kind); }
function state(step: Step, events: Event[], actionRequired = false): { status: PipelineStatus; event?: Event } {
  const history = events.filter((event) => relevant(step, event)).sort((a, b) => a.sequence - b.sequence);
  const latest = history.at(-1);
  const terminal = [...history].reverse().find((event) => [...step.completed, ...step.failed, ...step.blocked].includes(event.event_type));
  if (!latest) return { status: "pending" };
  const event = terminal && terminal.sequence < latest.sequence ? terminal : latest;
  return { status: step.completed.includes(event.event_type) ? "completed" : step.failed.includes(event.event_type) ? "failed" : step.blocked.includes(event.event_type) ? "blocked" : step.id === "source-approval" && actionRequired ? "action required" : "running", event };
}
function command(event?: Event) { const value = event?.payload.command; return typeof value === "string" ? value : null; }
function artifacts(event?: Event) { return [event?.payload.artifact_id, event?.payload.stdout_artifact_id, event?.payload.stderr_artifact_id].filter((value): value is string => typeof value === "string"); }

export function PipelineSection({ state: run, retryError, onRetry, retrying, qualificationAvailable = false, qualificationActionRequired = false, g02ActionRequired = false, focusStage, children }: { state: AuthoritativeRunStateDto; retryError: string | null; onRetry: () => void; retrying: boolean; qualificationAvailable?: boolean; qualificationActionRequired?: boolean; g02ActionRequired?: boolean; focusStage?: PipelineStepId; children?: (selectedStage: PipelineStepId | undefined) => ReactNode }) {
  const visible = qualificationAvailable || run.workflow_events.some((event) => ["BASELINE_QUALIFIED", "BASELINE_QUALIFIED_WITH_KNOWN_FAILURES", "G03_CREATED"].includes(event.event_type)) ? steps : steps.slice(0, -1);
  const statuses = visible.map((step) => state(step, run.workflow_events, g02ActionRequired));
  const qualificationIndex = visible.findIndex((step) => step.id === "baseline-qualification");
  const focusIndex = visible.findIndex((step) => step.id === focusStage);
  const g02Index = visible.findIndex((step) => step.id === "source-approval");
  const [selected, setSelected] = useState(focusIndex >= 0 ? focusIndex : qualificationActionRequired ? qualificationIndex : g02Index >= 0 && statuses[g02Index].status === "action required" ? g02Index : statuses.findIndex((item) => item.status === "running" || item.status === "failed"));
  const selectedIndex = selected >= 0 && selected < visible.length ? selected : Math.max(0, statuses.findIndex((item) => item.status === "pending"));
  const completed = statuses.filter((item) => item.status === "completed").length;
  const qualificationSelected = visible[selectedIndex]?.id === "baseline-qualification";
  useEffect(() => { if (qualificationActionRequired && qualificationIndex >= 0) setSelected(qualificationIndex); }, [qualificationActionRequired, qualificationIndex]);
  useEffect(() => { if (focusStage && focusIndex >= 0) setSelected(focusIndex); }, [focusIndex, focusStage]);
  return <section className={styles.pipelineSection} aria-label="Migration workflow progress">
    <div className={styles.pipelineSummary}><div><span className={styles.kicker}>Authoritative progression</span><h3>{visible[selectedIndex]?.label ?? "No active stage"}</h3><p>{completed} of {visible.length} stages complete · Last update {run.updated_at}</p></div><strong>{run.run_phase}</strong></div>
    {retryError ? <p role="alert">{retryError}</p> : null}
    <ol className={styles.stageList}>{visible.map((step, index) => { const current = statuses[index]; const isOpen = selectedIndex === index; return <li key={step.id} aria-label={`${step.label}: ${current.status}`} className={`${styles.stageRow} ${styles[`stage${current.status[0].toUpperCase()}${current.status.slice(1)}`]}`}>
      <button type="button" className={styles.stageButton} onClick={() => setSelected(index)} aria-expanded={isOpen}><span className={styles.stageMarker}>{current.status === "completed" ? "✓" : String(index + 1).padStart(2, "0")}</span><span><strong>{step.label}</strong>{step.gate ? <small className={styles.gateBadge}>Gate {step.gate}</small> : null}<small>{current.status}{current.event ? ` · ${current.event.occurred_at}` : ""}</small></span><span aria-hidden="true">{isOpen ? "−" : "+"}</span></button>
      {isOpen ? <div className={styles.stageDetails}><div className={styles.stageTabs}><span>Summary</span><span>Command output</span><span>Artifacts</span></div>{current.event ? <><p>{typeof current.event.payload.message === "string" ? current.event.payload.message : `Latest authoritative event: ${current.event.event_type}`}</p>{command(current.event) ? <details><summary>Command output</summary><pre className={styles.rawLog}>{typeof current.event.payload.chunk === "string" ? current.event.payload.chunk : command(current.event)}</pre></details> : null}{artifacts(current.event).length ? <p>Artifacts: {artifacts(current.event).map((id) => <a key={id} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a>)}</p> : null}</> : <p>Pending authoritative evidence.</p>}{index === 0 && current.status === "failed" ? <button type="button" onClick={onRetry} disabled={retrying}>{retrying ? "Retrying…" : "Retry source intake"}</button> : null}</div> : null}
    </li>; })}</ol>
    {children ? <div hidden={!qualificationSelected && visible[selectedIndex]?.id !== "source-approval"} aria-label={qualificationSelected ? "G03 review" : "G02 review"}>{children(visible[selectedIndex]?.id)}</div> : null}
  </section>;
}