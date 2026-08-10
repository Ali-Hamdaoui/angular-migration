import type { SourceAnalysisResult } from "@/api/migrations";
import type { PathValidationResult } from "@/types/generated/api";

export type SetupStep = "project" | "readiness" | "source-review" | "create-run";
export type ReadinessState = "waiting" | "running" | "passed" | "warning" | "blocked" | "unavailable" | "outdated";

export interface SetupBinding {
  revision: number;
  pathValidationId: string;
  environmentSnapshotId: string;
  sourceAnalysisId: string;
  preflightId: string;
}

export type ReadinessLifecycle = "waiting" | "running" | "unavailable" | "outdated";
export type SetupOperation = "path" | "environment" | "source" | "preflight";

export interface SetupOperationRow {
  id: SetupOperation;
  label: string;
  waitingCopy: string;
  runningCopy: string;
}

export const setupOperationRows: readonly SetupOperationRow[] = [
  {
    id: "path",
    label: "Path safety and target reservation",
    waitingCopy: "Waiting to verify the read-only source boundary and external target.",
    runningCopy: "Checking source and target safety and reserving the future output root.",
  },
  {
    id: "environment",
    label: "Environment capability",
    waitingCopy: "Waiting for path safety before checking the migration environment.",
    runningCopy: "Refreshing authoritative runtime, storage, and network capability evidence.",
  },
  {
    id: "source",
    label: "Source analysis",
    waitingCopy: "Waiting for path safety before analyzing the source workspace.",
    runningCopy: "Analyzing versions, package metadata, and workspace topology.",
  },
  {
    id: "preflight",
    label: "Production preflight",
    waitingCopy: "Waiting for all required readiness identifiers.",
    runningCopy: "Creating the production preflight bound to this exact evidence chain.",
  },
];

function mappedState(
  status: string | null | undefined,
  mapping: Readonly<Record<string, ReadinessState>>,
  lifecycle?: ReadinessLifecycle,
): ReadinessState {
  if (lifecycle) return lifecycle;
  return status !== null && status !== undefined && Object.prototype.hasOwnProperty.call(mapping, status)
    ? mapping[status]
    : "unavailable";
}

export function pathReadinessState(status: string | null | undefined, lifecycle?: ReadinessLifecycle): ReadinessState {
  return mappedState(status, {
    passed: "passed",
    passed_with_warnings: "warning",
    blocked: "blocked",
  }, lifecycle);
}

export function environmentReadinessState(status: string | null | undefined, lifecycle?: ReadinessLifecycle): ReadinessState {
  return mappedState(status, {
    available: "passed",
    degraded: "warning",
    blocked: "blocked",
  }, lifecycle);
}

export function sourceReadinessState(status: string | null | undefined, lifecycle?: ReadinessLifecycle): ReadinessState {
  return mappedState(status, {
    accepted: "passed",
    review_required: "warning",
    blocked: "blocked",
  }, lifecycle);
}

export function preflightReadinessState(status: string | null | undefined, lifecycle?: ReadinessLifecycle): ReadinessState {
  return mappedState(status, {
    passed: "passed",
    passed_with_warnings: "warning",
    blocked: "blocked",
    expired: "outdated",
    stale: "outdated",
  }, lifecycle);
}

export const readinessStateLabels: Readonly<Record<ReadinessState, string>> = {
  waiting: "Waiting",
  running: "Running",
  passed: "Passed",
  warning: "Warning",
  blocked: "Blocked",
  unavailable: "Unavailable",
  outdated: "Outdated",
};

const unavailableEvidence = "Not available from readiness evidence";

export interface SourceReviewSummary {
  angularVersion: string;
  workspaceTopology: string;
  packageManager: string;
  projectCount: string;
  builderName: string;
  customBuilderDetected: "Yes" | "No" | "Not available from readiness evidence";
  lockfile: string;
  evidenceConfidence: string;
  reservedTarget: string;
  warnings: string[];
}

function evidenceValue(value: string | null | undefined): string {
  return value?.trim() ? value : unavailableEvidence;
}

export function buildSourceReviewSummary(
  analysis: SourceAnalysisResult | null,
  pathValidation: PathValidationResult | null,
): SourceReviewSummary {
  const snapshot = analysis?.snapshot;
  const angularCore = snapshot?.versions.find((version) => version.package === "@angular/core");

  return {
    angularVersion: evidenceValue(angularCore?.resolved ?? angularCore?.declared ?? angularCore?.family),
    workspaceTopology: evidenceValue(snapshot?.topology.classification),
    packageManager: evidenceValue(snapshot?.package_manager),
    projectCount: snapshot ? String(snapshot.topology.projects.length) : unavailableEvidence,
    builderName: unavailableEvidence,
    customBuilderDetected: snapshot ? snapshot.topology.has_custom_builder ? "Yes" : "No" : unavailableEvidence,
    lockfile: evidenceValue(snapshot?.lockfile),
    evidenceConfidence: evidenceValue(angularCore?.confidence),
    reservedTarget: evidenceValue(pathValidation?.snapshot.resolved_output_root),
    warnings: snapshot ? [...snapshot.warnings] : [],
  };
}
