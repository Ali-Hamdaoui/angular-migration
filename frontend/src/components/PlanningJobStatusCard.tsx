import { getBackendBaseUrl } from "@/api/client";
import type { ArtifactRefDto, PlanningJobProjectionDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

const statusLabels: Record<string, string> = {
  queued_after_g04: "Planning queued",
  resolving_feasibility: "Resolving feasibility inputs",
  waiting_g05: "Waiting for G05 review",
  generating_plan: "Generating migration plan",
  running_planning_review: "Reviewing migration plan",
  waiting_g06: "Waiting for G06 review",
  waiting_retry: "Automatic retry scheduled",
  completed: "Planning approved",
  completed_blocked: "Planning completed with a blocking outcome",
  technical_failed: "Planning failed",
};

function remediation(code?: string | null): string | null {
  if (!code) return null;
  if (code === "PLANNING_WORKSPACE_FINGERPRINT_MISMATCH") return "Restore the approved physical workspace or regenerate and reapprove the fingerprint-bound evidence before resolving again.";
  if (code === "PLANNING_WORKSPACE_FINGERPRINT_MISSING") return "Regenerate authoritative G03/G04/G05 evidence so planning is bound to a physical workspace fingerprint.";
  if (code.startsWith("PACKAGE_JSON_")) return "Correct package.json using the parser location in the diagnostic evidence, then resolve feasibility again.";
  if (code.startsWith("WORKSPACE_JSON_") || code === "ANGULAR_PROJECTS_INVALID" || code === "ANGULAR_PROJECT_INVALID") return "Correct angular.json using the backend parser diagnostics, then resolve feasibility again.";
  if (code === "AMBIGUOUS_ANGULAR_PROJECT_SELECTION") return "Configure or select one authoritative Angular application; do not assume the first project is valid.";
  if (code === "UNSUPPORTED_PACKAGE_MANAGER") return "The current authoritative planner supports npm workspaces only. Convert the controlled workspace or add backend support before retrying.";
  if (code.includes("TRANSIENT") || code === "PLANNING_WORKER_INTERRUPTED") return "The backend owns recovery for this transient failure. Keep the page connected and wait for the scheduled retry.";
  return "Review the failure stage, correlation ID, and immutable diagnostic evidence before issuing another backend command.";
}

export function PlanningJobStatusCard({ job, artifacts = [] }: { job?: PlanningJobProjectionDto | null; artifacts?: ArtifactRefDto[] }) {
  if (!job) return null;
  const failureArtifact = artifacts.find((artifact) => artifact.relative_path.endsWith("03_planning/planning-input-resolution-failure.json"));
  const isAlert = job.status === "technical_failed" || job.status === "completed_blocked";
  const guidance = remediation(job.last_error_code);
  return <section className={styles.previewPanel} aria-labelledby={`planning-progress-${job.id}`} role={isAlert ? "alert" : undefined}>
    <div className={styles.previewHeader}>
      <div><p className={styles.kicker}>Authoritative planning job</p><h3 id={`planning-progress-${job.id}`}>Planning progress</h3></div>
      <span className={styles.status}>{statusLabels[job.status] ?? job.status}</span>
    </div>
    <div className={styles.dimensionGrid}>
      <div><span>Step</span><strong>{job.current_step}</strong></div>
      <div><span>Attempt</span><strong>Attempt {job.attempt} of {job.max_attempts}</strong></div>
      <div><span>Last update</span><strong>{job.updated_at || "unavailable"}</strong></div>
      <div><span>Correlation ID</span><code>{job.correlation_id ?? "unavailable"}</code></div>
    </div>
    {job.status === "waiting_retry" ? <p role="status">Automatic retry scheduled{job.next_attempt_at ? ` for ${job.next_attempt_at}` : ""}. No manual retry is required.</p> : null}
    {job.last_error_code ? <div>
      <p><strong>Error:</strong> <code>{job.last_error_code}</code>{job.last_error_stage ? <> at <code>{job.last_error_stage}</code></> : null}</p>
      {job.last_error_message ? <p>{job.last_error_message}</p> : null}
      {guidance ? <p className={styles.note}>{guidance}</p> : null}
    </div> : null}
    {failureArtifact ? <a className={styles.actionLink} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(failureArtifact.artifact_id)}`} target="_blank" rel="noreferrer">Open planning failure evidence</a> : null}
  </section>;
}
