/**
 * Presentation helpers for formatting backend status, phase, and event values
 * into user-facing labels.
 *
 * These functions are pure and never mutate the original value. Formatted
 * values must never be used for workflow decisions; raw values remain
 * available in diagnostic and evidence views.
 */

const STATUS_LABELS: Record<string, string> = {
  SOURCE_VALIDATED: "Source validated",
  WAITING: "Waiting for approval",
  RUNNING: "In progress",
  COMPLETED: "Completed",
  FAILED: "Failed",
  BLOCKED: "Blocked",
  pending: "Pending approval",
  approved: "Approved",
  rejected: "Rejected",
  stale: "Needs refresh",
};

const PHASE_LABELS: Record<string, string> = {
  PREFLIGHT_SNAPSHOT: "Source snapshot",
  SOURCE_VALIDATION: "Source validation",
  G02_REVIEW: "Source approval",
  BASELINE_PREPARATION: "Baseline preparation",
  BASELINE_INSTALLATION: "Baseline installation",
  BASELINE_VALIDATION: "Baseline checks",
  G03_REVIEW: "Baseline approval",
  DISCOVERY: "Project discovery",
  ANALYSIS: "Analysis review",
  FEASIBILITY: "Compatibility review",
  PLANNING: "Migration plan",
  G06_REVIEW: "Plan approval",
  TRANSFORMATION: "Migration execution",
};

const EVENT_LABELS: Record<string, string> = {
  RUN_CREATED: "Run created",
  SOURCE_INTAKE_QUEUED: "Source intake queued",
  SOURCE_INTAKE_STARTED: "Source intake started",
  SOURCE_INTAKE_COMPLETED: "Source intake completed",
  SOURCE_INTAKE_FAILED: "Source intake failed",
  SNAPSHOT_STARTED: "Snapshot started",
  SNAPSHOT_CREATED: "Snapshot created",
  SNAPSHOT_FAILED: "Snapshot failed",
  SNAPSHOT_QUARANTINED: "Snapshot quarantined",
  G02_CREATED: "Source approval created",
  G02_APPROVED: "Source approved",
  G02_REJECTED: "Source rejected",
  G02_STALE: "Source approval needs refresh",
  SOURCE_INTEGRITY_VERIFIED: "Source integrity verified",
  SOURCE_INTEGRITY_FAILED: "Source integrity failed",
  EXECUTION_PROFILE_RESOLUTION_STARTED: "Runtime resolution started",
  EXECUTION_PROFILE_RESOLVED: "Runtime resolved",
  EXECUTION_PROFILE_SELECTED: "Runtime selected",
  EXECUTION_PROFILE_BLOCKED: "Runtime blocked",
  BASELINE_WORKSPACE_STARTED: "Baseline workspace started",
  BASELINE_WORKSPACE_READY: "Baseline workspace ready",
  BASELINE_INSTALL_SUCCEEDED: "Dependencies installed",
  BASELINE_INSTALL_FAILED: "Dependency installation failed",
  BASELINE_INSTALL_BLOCKED: "Dependency installation blocked",
  BASELINE_BUILD_STARTED: "Baseline build started",
  BASELINE_BUILD_COMPLETED: "Baseline build completed",
  BASELINE_TESTS_STARTED: "Baseline tests started",
  BASELINE_TESTS_COMPLETED: "Baseline tests completed",
  BASELINE_LINT_STARTED: "Baseline lint started",
  BASELINE_LINT_COMPLETED: "Baseline lint completed",
  BASELINE_QUALIFIED: "Baseline qualified",
  BASELINE_QUALIFIED_WITH_KNOWN_FAILURES: "Baseline qualified with known failures",
  BASELINE_BLOCKED: "Baseline blocked",
  G03_CREATED: "Baseline approval created",
  G03_APPROVED: "Baseline approved",
  G03_REJECTED: "Baseline rejected",
  DISCOVERY_STARTED: "Discovery started",
  DISCOVERY_COMPLETED: "Discovery completed",
  DISCOVERY_BLOCKED: "Discovery blocked",
  ANALYSIS_AGENT_STARTED: "Analysis started",
  ANALYSIS_AGENT_COMPLETED: "Analysis completed",
  ANALYSIS_AGENT_FAILED: "Analysis failed",
  G04_CREATED: "Analysis approval created",
  G04_APPROVED: "Analysis approved",
  G04_REJECTED: "Analysis rejected",
  COMPATIBILITY_RESOLUTION_STARTED: "Compatibility resolution started",
  COMPATIBILITY_RESOLUTION_COMPLETED: "Compatibility resolution completed",
  COMPATIBILITY_RESOLUTION_BLOCKED: "Compatibility resolution blocked",
  G05_CREATED: "Compatibility approval created",
  G05_APPROVED: "Compatibility approved",
  G05_REJECTED: "Compatibility rejected",
  MIGRATION_PLAN_CREATED: "Migration plan created",
  STAGE_PLAN_CREATED: "Stage plan created",
  PLAN_REVISION_CREATED: "Plan revision created",
  G06_CREATED: "Plan approval created",
  G06_APPROVED: "Plan approved",
  G06_REJECTED: "Plan rejected",
  COMMAND_QUEUED: "Command queued",
  COMMAND_STARTED: "Command started",
  COMMAND_OUTPUT_CHUNK: "Command output",
  COMMAND_SUCCEEDED: "Command succeeded",
  COMMAND_FAILED: "Command failed",
  COMMAND_INTERRUPTED: "Command interrupted",
  COMMAND_CANCELLED: "Command cancelled",
  PARITY_BASELINE_STARTED: "Parity baseline started",
  PARITY_BASELINE_COMPLETED: "Parity baseline completed",
  PARITY_BASELINE_BLOCKED: "Parity baseline blocked",
  BASELINE_FAILURES_FINGERPRINTED: "Baseline failures fingerprinted",
};

function sentenceCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .toLowerCase()
    .replace(/^\w/, (char) => char.toUpperCase());
}

export function formatStatusLabel(value: string): string {
  return STATUS_LABELS[value] ?? sentenceCase(value);
}

export function formatPhaseLabel(value: string): string {
  return PHASE_LABELS[value] ?? sentenceCase(value);
}

export function formatEventLabel(value: string): string {
  return EVENT_LABELS[value] ?? sentenceCase(value);
}