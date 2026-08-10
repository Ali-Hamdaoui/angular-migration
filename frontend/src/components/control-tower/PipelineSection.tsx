"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { JourneyKey } from "@/presentation/runJourney";
import { getBackendBaseUrl } from "@/api/client";
import styles from "./ControlTowerLayout.module.css";

type Event = AuthoritativeRunStateDto["workflow_events"][number];
type Step = { label: string; started: string[]; completed: string[]; failed: string[]; blocked: string[]; kind?: string };
type PipelineStatus = "pending" | "running" | "action required" | "completed" | "failed" | "blocked";

const steps: Step[] = [
  { label: "Source intake", started: ["SOURCE_INTAKE_QUEUED", "SOURCE_INTAKE_STARTED"], completed: ["SOURCE_INTAKE_COMPLETED"], failed: ["SOURCE_INTAKE_FAILED"], blocked: [] },
  { label: "Source snapshot", started: ["SNAPSHOT_STARTED", "SNAPSHOT_PROGRESS_UPDATED"], completed: ["SNAPSHOT_CREATED"], failed: ["SNAPSHOT_FAILED", "SNAPSHOT_QUARANTINED"], blocked: [] },
  { label: "Source review & G02", started: ["G02_CREATED"], completed: ["G02_APPROVED"], failed: ["G02_REJECTED"], blocked: ["G02_STALE", "SOURCE_INTEGRITY_FAILED"] },
  { label: "Runtime validation", started: ["EXECUTION_PROFILE_RESOLUTION_STARTED"], completed: ["EXECUTION_PROFILE_RESOLVED", "EXECUTION_PROFILE_SELECTED"], failed: [], blocked: ["EXECUTION_PROFILE_BLOCKED"] },
  { label: "Baseline preparation", started: ["BASELINE_WORKSPACE_STARTED"], completed: ["BASELINE_WORKSPACE_READY"], failed: [], blocked: ["BASELINE_INSTALL_BLOCKED"] },
  { label: "Dependency installation", started: ["COMMAND_QUEUED", "COMMAND_STARTED", "COMMAND_OUTPUT_CHUNK"], completed: ["BASELINE_INSTALL_SUCCEEDED"], failed: ["BASELINE_INSTALL_FAILED", "COMMAND_INTERRUPTED", "COMMAND_CANCELLED"], blocked: [] },
  { label: "Build", started: ["BASELINE_BUILD_STARTED", "COMMAND_OUTPUT_CHUNK"], completed: ["BASELINE_BUILD_COMPLETED"], failed: [], blocked: [], kind: "build" },
  { label: "Tests", started: ["BASELINE_TESTS_STARTED", "COMMAND_OUTPUT_CHUNK"], completed: ["BASELINE_TESTS_COMPLETED"], failed: [], blocked: [], kind: "test" },
  { label: "Lint", started: ["BASELINE_LINT_STARTED", "COMMAND_OUTPUT_CHUNK"], completed: ["BASELINE_LINT_COMPLETED"], failed: [], blocked: [], kind: "lint" },
  { label: "Baseline qualification", started: [], completed: ["BASELINE_QUALIFIED", "BASELINE_QUALIFIED_WITH_KNOWN_FAILURES"], failed: [], blocked: ["BASELINE_BLOCKED"] },
  { label: "G03 readiness", started: [], completed: ["G03_CREATED"], failed: [], blocked: [] },
];

const FOCUS_STAGE_LABELS: Record<JourneyKey, string> = {
  setup: "Source intake",
  readiness: "Source review & G02",
  g01: "Source review & G02",
  baseline: "Baseline qualification",
  discovery: "G03 readiness",
  feasibility: "G03 readiness",
  plan: "G03 readiness",
  "18-to-19": "G03 readiness",
  "19-to-20": "G03 readiness",
  "20-to-21": "G03 readiness",
  validate: "G03 readiness",
  complete: "G03 readiness",
};

function relevant(step: Step, event: Event) { return [...step.started, ...step.completed, ...step.failed, ...step.blocked].includes(event.event_type) && (event.event_type !== "COMMAND_OUTPUT_CHUNK" || !step.kind || event.payload.kind === step.kind); }
function state(step: Step, events: Event[], actionRequired = false): { status: PipelineStatus; event?: Event } {
  const history = events.filter((event) => relevant(step, event)).sort((a, b) => a.sequence - b.sequence);
  const latest = history.at(-1);
  const terminal = [...history].reverse().find((event) => [...step.completed, ...step.failed, ...step.blocked].includes(event.event_type));
  if (!latest) return { status: "pending" };
  const event = terminal && terminal.sequence < latest.sequence ? terminal : latest;
  return { status: step.completed.includes(event.event_type) ? "completed" : step.failed.includes(event.event_type) ? "failed" : step.blocked.includes(event.event_type) ? "blocked" : step.label === "Source review & G02" && actionRequired ? "action required" : "running", event };
}
function command(event?: Event) { const value = event?.payload.command; return typeof value === "string" ? value : null; }
function artifacts(event?: Event) { return [event?.payload.artifact_id, event?.payload.stdout_artifact_id, event?.payload.stderr_artifact_id].filter((value): value is string => typeof value === "string"); }

export function PipelineSection({ state: run, retryError, onRetry, retrying, qualificationAvailable = false, qualificationActionRequired = false, g02ActionRequired = false, focusStage, children }: { state: AuthoritativeRunStateDto; retryError: string | null; onRetry: () => void; retrying: boolean; qualificationAvailable?: boolean; qualificationActionRequired?: boolean; g02ActionRequired?: boolean; focusStage?: JourneyKey; children?: (selectedStage: string | undefined) => ReactNode }) {
  const visible = qualificationAvailable || run.workflow_events.some((event) => ["BASELINE_QUALIFIED", "BASELINE_QUALIFIED_WITH_KNOWN_FAILURES", "G03_CREATED"].includes(event.event_type)) ? steps : steps.slice(0, -1);
  const statuses = visible.map((step) => state(step, run.workflow_events, g02ActionRequired));
  const qualificationIndex = visible.findIndex((step) => step.label === "Baseline qualification");
  const focusIndex = focusStage == null ? -1 : visible.findIndex((step) => step.label === FOCUS_STAGE_LABELS[focusStage]);
  const g02Index = visible.findIndex((step) => step.label === "Source review & G02");
  const [selected, setSelected] = useState(focusIndex >= 0 ? focusIndex : qualificationActionRequired ? qualificationIndex : g02Index >= 0 && statuses[g02Index].status === "action required" ? g02Index : statuses.findIndex((item) => item.status === "running" || item.status === "failed"));
  const selectedIndex = selected >= 0 && selected < visible.length ? selected : Math.max(0, statuses.findIndex((item) => item.status === "pending"));
  const completed = statuses.filter((item) => item.status === "completed").length;
  const qualificationSelected = visible[selectedIndex]?.label === "Baseline qualification";
  useEffect(() => { if (qualificationActionRequired && qualificationIndex >= 0) setSelected(qualificationIndex); }, [qualificationActionRequired, qualificationIndex]);
  useEffect(() => { if (focusStage && focusIndex >= 0) setSelected(focusIndex); }, [focusIndex, focusStage]);
  return <section className={styles.pipelineSection} aria-label="Migration workflow progress">
    <div className={styles.pipelineSummary}><div><span className={styles.kicker}>Authoritative progression</span><h3>{visible[selectedIndex]?.label ?? "No active stage"}</h3><p>{completed} of {visible.length} stages complete · Last update {run.updated_at}</p></div><strong>{run.run_phase}</strong></div>
    {retryError ? <p role="alert">{retryError}</p> : null}
    <ol className={styles.stageList}>{visible.map((step, index) => { const current = statuses[index]; const isOpen = selectedIndex === index; return <li key={step.label} aria-label={`${step.label}: ${current.status}`} className={`${styles.stageRow} ${styles[`stage${current.status[0].toUpperCase()}${current.status.slice(1)}`]}`}>
      <button type="button" className={styles.stageButton} onClick={() => setSelected(index)} aria-expanded={isOpen}><span className={styles.stageMarker}>{current.status === "completed" ? "✓" : String(index + 1).padStart(2, "0")}</span><span><strong>{step.label}</strong><small>{current.status}{current.event ? ` · ${current.event.occurred_at}` : ""}</small></span><span aria-hidden="true">{isOpen ? "−" : "+"}</span></button>
      {isOpen ? <div className={styles.stageDetails}><div className={styles.stageTabs}><span>Summary</span><span>Command output</span><span>Artifacts</span></div>{current.event ? <><p>{typeof current.event.payload.message === "string" ? current.event.payload.message : `Latest authoritative event: ${current.event.event_type}`}</p>{command(current.event) ? <details><summary>Command output</summary><pre className={styles.rawLog}>{typeof current.event.payload.chunk === "string" ? current.event.payload.chunk : command(current.event)}</pre></details> : null}{artifacts(current.event).length ? <p>Artifacts: {artifacts(current.event).map((id) => <a key={id} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a>)}</p> : null}</> : <p>Pending authoritative evidence.</p>}{index === 0 && current.status === "failed" ? <button type="button" onClick={onRetry} disabled={retrying}>{retrying ? "Retrying…" : "Retry source intake"}</button> : null}</div> : null}
    </li>; })}</ol>
    {children ? <div hidden={!qualificationSelected && visible[selectedIndex]?.label !== "Source review & G02"} aria-label={qualificationSelected ? "G03 review" : "G02 review"}>{children(visible[selectedIndex]?.label)}</div> : null}
  </section>;
}
