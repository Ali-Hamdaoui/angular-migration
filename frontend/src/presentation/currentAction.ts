import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import { gateDefinition, isGateId, type GateId } from "@/presentation/gates";
import {
  buildJourney,
  type JourneyKey,
  type JourneyMilestone,
  type TransformationLoadStatus,
} from "@/presentation/runJourney";
import { presentStatus } from "@/presentation/status";
import type { AuthoritativeRunStateDto, WorkflowEventDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";

export interface CurrentAction {
  kind: "gate" | "blocked" | "running" | "complete" | "unavailable";
  gateId?: GateId;
  title: string;
  summary: string;
  consequence?: string;
  section: "overview" | "pipeline" | "evidence" | "diagnostics";
  stageKey?: JourneyKey;
  evidenceIds: string[];
  rawSource: string;
}

export interface RunWorkspaceProjection {
  journey: JourneyMilestone[];
  currentAction: CurrentAction;
  completed: string;
  now: string;
  next: string;
}

const RUN_GATE_IDS = ["G02", "G03", "G04", "G05", "G06"] as const;
const TRANSFORMATION_GATE_IDS: GateId[] = ["G07", "G08", "G09", "G10", "G11", "G12"];
const BLOCKING_TRANSFORMATION_STATUSES = ["blocked", "failed"];
const BLOCKING_STAGE_STATUSES = ["FAILED", "ROLLED_BACK", "CANCELLED", "DIAGNOSTIC_HOLD"];
const TERMINAL_GATE_SUFFIXES = [
  "APPROVED",
  "APPROVED_WITH_RISK",
  "REJECTED",
  "MODIFICATION_REQUESTED",
  "STALE",
  "EXPIRED",
  "CANCELLED",
] as const;

function versionMajor(version: string | null): number | null {
  const match = version?.match(/\d+/);
  return match ? Number(match[0]) : null;
}

function stageKeyForTransformation(transformation: TransformationProjection): JourneyKey | undefined {
  const route = `${versionMajor(transformation.source_version)}-${versionMajor(transformation.target_version)}`;
  if (route === "18-19") return "18-to-19";
  if (route === "19-20") return "19-to-20";
  if (route === "20-21") return "20-to-21";
  return undefined;
}

function stageKeyForGate(gateId: GateId): JourneyKey | undefined {
  if (gateId === "G02" || gateId === "G03") return "baseline";
  if (gateId === "G04") return "discovery";
  if (gateId === "G05") return "feasibility";
  if (gateId === "G06") return "plan";
  return undefined;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.length > 0) : [];
}

function pendingRunGate(run: AuthoritativeRunStateDto): { gateId: GateId; event: WorkflowEventDto } | null {
  const ordered = [...run.workflow_events].sort((left, right) => left.sequence - right.sequence);
  const created = ordered
    .filter((event) => RUN_GATE_IDS.some((gateId) => event.event_type === `${gateId}_CREATED`))
    .at(-1);
  if (!created) return null;

  const gateId = created.event_type.slice(0, 3) as GateId;
  const isTerminal = ordered.some((event) =>
    event.sequence > created.sequence
    && TERMINAL_GATE_SUFFIXES.some((suffix) => event.event_type === `${gateId}_${suffix}`),
  );
  if (isTerminal) return null;

  const payload = created.payload;
  const hasBindings = payload.gate_id === gateId
    && typeof payload.package_checksum === "string"
    && payload.package_checksum.length > 0
    && typeof payload.expected_state_version === "number"
    && Number.isFinite(payload.expected_state_version)
    && payload.expected_state_version === run.state_version
    && stringArray(payload.permitted_decisions).length > 0;
  return hasBindings ? { gateId, event: created } : null;
}

function gateAction(
  gateId: GateId,
  rawSource: string,
  evidenceIds: string[],
  stageKey?: JourneyKey,
): CurrentAction {
  const definition = gateDefinition(gateId);
  return {
    kind: "gate",
    gateId,
    title: `${definition.label} required`,
    summary: definition.purpose,
    consequence: definition.decision,
    section: gateId === "G01" ? "overview" : "pipeline",
    ...(stageKey ? { stageKey } : {}),
    evidenceIds,
    rawSource,
  };
}

function transformationGateAction(transformation: TransformationProjection): CurrentAction | null {
  if (
    transformation.status.toLowerCase() !== "waiting_gate"
    || !isGateId(transformation.active_gate)
    || !TRANSFORMATION_GATE_IDS.includes(transformation.active_gate)
    || !transformation.active_gate_package_checksum?.trim()
    || !transformation.workspace_fingerprint?.trim()
    || !Number.isFinite(transformation.state_version)
    || transformation.state_version < 1
  ) {
    return null;
  }

  return gateAction(
    transformation.active_gate,
    `transformation:${transformation.continuation_id}:${transformation.active_gate}`,
    [transformation.continuation_id, transformation.stage_id],
    stageKeyForTransformation(transformation),
  );
}

function refreshAction(rawSource: string): CurrentAction {
  return {
    kind: "unavailable",
    title: "Authoritative state is refreshing",
    summary: "Confirmed journey state remains visible while authoritative records are refreshed.",
    consequence: "Decision controls are withheld until the backend bindings are current.",
    section: "diagnostics",
    evidenceIds: [],
    rawSource,
  };
}

function transformationAction(transformation: TransformationProjection): CurrentAction | null {
  const status = transformation.status.toLowerCase();
  const stageKey = stageKeyForTransformation(transformation);
  const common = {
    section: "pipeline" as const,
    stageKey,
    evidenceIds: [transformation.continuation_id, transformation.stage_id],
  };

  if (BLOCKING_TRANSFORMATION_STATUSES.includes(status) || BLOCKING_STAGE_STATUSES.includes(transformation.stage_status)) {
    return {
      ...common,
      kind: "blocked",
      title: "Transformation blocked",
      summary: transformation.active_error?.message || transformation.last_error_message || "The backend has blocked transformation work.",
      consequence: "Inspect the authoritative blocker before attempting to continue.",
      rawSource: transformation.active_error?.code || transformation.last_error_code || `transformation:${status}`,
    };
  }

  if (status === "waiting_gate") {
    return {
      ...common,
      kind: "unavailable",
      title: "Transformation gate bindings unavailable",
      summary: "A human gate is pending, but its exact backend decision bindings are unavailable.",
      consequence: "Decision controls remain withheld until the package bindings are complete.",
      rawSource: `transformation:${status}:${transformation.active_gate ?? "unknown_gate"}`,
    };
  }

  if (status === "waiting_prompt" || transformation.active_prompt_id) {
    return {
      ...common,
      kind: "blocked",
      title: "Command input required",
      summary: transformation.active_prompt_text || transformation.active_prompt_explanation?.summary || "The migration command is waiting for backend-confirmed input.",
      consequence: "Transformation remains paused until the prompt is resolved.",
      evidenceIds: [...common.evidenceIds, ...(transformation.active_prompt_id ? [transformation.active_prompt_id] : [])],
      rawSource: `transformation:${status}:prompt`,
    };
  }

  const commandStatus = transformation.active_command_status?.toLowerCase();
  if (transformation.active_command_id && commandStatus && ["queued", "pending", "running"].includes(commandStatus)) {
    return {
      ...common,
      kind: "running",
      title: "Migration command running",
      summary: "The backend is executing the current migration command.",
      evidenceIds: [...common.evidenceIds, transformation.active_command_id],
      rawSource: `command:${transformation.active_command_id}:${commandStatus}`,
    };
  }

  return null;
}

function runBlockerAction(run: AuthoritativeRunStateDto): CurrentAction | null {
  const status = run.status.toString();
  const phaseStatus = run.phase_status.toLowerCase();
  const failure = phaseStatus === "failed"
    || phaseStatus === "blocked"
    || ["FAILED", "DIAGNOSTIC_HOLD", "ORPHANED", "WORKER_LOST", "CLEANUP_FAILED", "TIMED_OUT"].includes(status);
  if (failure) {
    return {
      kind: "blocked",
      title: "Run failed",
      summary: "The authoritative run snapshot reports blocked or failed work.",
      consequence: "Inspect Diagnostics before continuing.",
      section: "diagnostics",
      evidenceIds: [],
      rawSource: `run:${status}:${run.phase_status}`,
    };
  }
  if (run.approval_status === "pending" || phaseStatus === "waiting_approval") {
    return {
      kind: "blocked",
      title: "Run approval required",
      summary: "The backend reports a pending approval without a complete decision binding package.",
      consequence: "Open the relevant pipeline stage to inspect the authoritative review state.",
      section: "pipeline",
      evidenceIds: [],
      rawSource: `run:${status}:${run.approval_status}`,
    };
  }
  return null;
}

function activeRunAction(run: AuthoritativeRunStateDto): CurrentAction | null {
  const status = run.status.toString();
  const active = run.phase_status.toLowerCase() === "running"
    || status === "RUNNING"
    || status.endsWith("_RUNNING")
    || ["RECOVERY_RUNNING", "RESUMING", "CANCELLING"].includes(status);
  if (!active) return null;

  const presented = presentStatus(status);
  return {
    kind: "running",
    title: presented.label,
    summary: `Authoritative run work is active in ${presentStatus(run.run_phase).label}.`,
    section: "pipeline",
    evidenceIds: [],
    rawSource: `run:${status}:${run.run_phase}:${run.phase_status}`,
  };
}

function verifiedCompleteAction(run: AuthoritativeRunStateDto): CurrentAction | null {
  const eventTypes = new Set(run.workflow_events.map((event) => event.event_type));
  if (!eventTypes.has("STAGED_MIGRATION_COMPLETED") || !eventTypes.has("FINAL_TARGET_VERIFIED")) return null;
  return {
    kind: "complete",
    title: "Migration verified complete",
    summary: "The staged migration and final target verification are durably recorded.",
    section: "overview",
    stageKey: "complete",
    evidenceIds: run.workflow_events
      .filter((event) => event.event_type === "STAGED_MIGRATION_COMPLETED" || event.event_type === "FINAL_TARGET_VERIFIED")
      .map((event) => event.event_id),
    rawSource: "STAGED_MIGRATION_COMPLETED+FINAL_TARGET_VERIFIED",
  };
}

export function selectCurrentAction(
  run: AuthoritativeRunStateDto,
  transformation: TransformationProjection | null,
  transformationStatus: TransformationLoadStatus,
  connection: AuthoritativeConnectionStatus,
): CurrentAction {
  if (connection === "recovering" || connection === "failed") return refreshAction(`connection:${connection}`);
  if (transformation && transformation.run_id !== run.run_id) return refreshAction("incompatible_run_id");

  if (transformation && transformationStatus === "ready") {
    const pendingTransformationGate = transformationGateAction(transformation);
    if (pendingTransformationGate) return pendingTransformationGate;
  }

  const pendingGate = pendingRunGate(run);
  if (pendingGate) {
    return gateAction(
      pendingGate.gateId,
      pendingGate.event.event_type,
      [pendingGate.event.event_id, ...stringArray(pendingGate.event.payload.evidence_ids)],
      stageKeyForGate(pendingGate.gateId),
    );
  }

  if (transformation && transformationStatus === "ready") {
    const selectedTransformationAction = transformationAction(transformation);
    if (selectedTransformationAction) return selectedTransformationAction;
  }

  return runBlockerAction(run)
    ?? activeRunAction(run)
    ?? verifiedCompleteAction(run)
    ?? {
      kind: "unavailable",
      title: "Current action unavailable",
      summary: "No current action can be confirmed from the authoritative facts available.",
      section: "diagnostics",
      evidenceIds: [],
      rawSource: `run:${run.status}:${run.phase_status}:unavailable`,
    };
}

export function summarizeCompleted(journey: JourneyMilestone[]): string {
  const completed = journey.filter((milestone) => milestone.state === "complete").map((milestone) => milestone.label);
  return completed.length ? completed.join(", ") : "No milestones confirmed complete";
}

export function summarizeNext(journey: JourneyMilestone[], currentAction: CurrentAction): string {
  if (currentAction.kind === "complete") return "No further milestone";
  const next = journey.find((milestone) => milestone.state === "blocked")
    ?? journey.find((milestone) => milestone.state === "action-required" || milestone.state === "current");
  return next?.label ?? "Next milestone unavailable";
}

export function buildRunWorkspaceProjection(
  run: AuthoritativeRunStateDto,
  transformation: TransformationProjection | null,
  transformationStatus: TransformationLoadStatus,
  connection: AuthoritativeConnectionStatus,
): RunWorkspaceProjection {
  const journey = buildJourney(run, transformation, transformationStatus);
  const currentAction = selectCurrentAction(run, transformation, transformationStatus, connection);
  return {
    journey,
    currentAction,
    completed: summarizeCompleted(journey),
    now: currentAction.title,
    next: summarizeNext(journey, currentAction),
  };
}
