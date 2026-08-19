import type { AuthoritativeRunStateDto, StageStatus, WorkflowEventDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";
import type { GateId } from "@/presentation/gates";

export type FixedJourneyKey =
  | "setup"
  | "readiness"
  | "g01"
  | "baseline"
  | "discovery"
  | "feasibility"
  | "plan"
  | "validate"
  | "complete";

export type StageJourneyKey = `stage:${string}`;

export type JourneyKey = FixedJourneyKey | StageJourneyKey;

export type JourneyState =
  | "complete"
  | "current"
  | "action-required"
  | "blocked"
  | "not-reached"
  | "unavailable";

export interface JourneyMilestone {
  key: JourneyKey;
  label: string;
  state: JourneyState;
  evidenceEvent?: string;
  evidenceEvents?: string[];
  stageId?: string;
}

export type TransformationLoadStatus = "disabled" | "loading" | "ready" | "empty" | "failed";
type AuthoritativeRouteStatus = StageStatus | "sealed";

export type ApprovedJourneyStage = {
  stageId: string;
  sourceMajor: number;
  targetMajor: number;
};

export type ApprovedJourneyRoute = ApprovedJourneyStage[];

export function isStageJourneyKey(key: JourneyKey): key is StageJourneyKey {
  return key.startsWith("stage:");
}

export function stageJourneyKey(stageId: string): StageJourneyKey {
  return `stage:${stageId}`;
}

const JOURNEY_LABELS: Record<FixedJourneyKey, string> = {
  setup: "Setup",
  readiness: "Readiness",
  g01: "Production readiness",
  baseline: "Baseline",
  discovery: "Discovery",
  feasibility: "Feasibility",
  plan: "Migration plan",
  validate: "Validate",
  complete: "Complete",
};

const PRE_TRANSFORMATION_KEYS: FixedJourneyKey[] = [
  "setup",
  "readiness",
  "g01",
  "baseline",
  "discovery",
  "feasibility",
  "plan",
];

const POST_TRANSFORMATION_KEYS: FixedJourneyKey[] = ["validate", "complete"];

const FIXED_JOURNEY_KEYS: FixedJourneyKey[] = [...PRE_TRANSFORMATION_KEYS, ...POST_TRANSFORMATION_KEYS];

const TERMINAL_SUFFIXES = [
  "APPROVED",
  "APPROVED_WITH_RISK",
  "REJECTED",
  "MODIFICATION_REQUESTED",
  "STALE",
  "EXPIRED",
  "CANCELLED",
] as const;
const ROUTE_STATUS_STATES = {
  PENDING: "not-reached",
  preparing: "current",
  RUNNING: "current",
  WAITING_APPROVAL: "action-required",
  REPAIRING: "current",
  PASSED: "complete",
  passed_with_known_baseline_failures: "complete",
  passed_with_manual_items: "complete",
  sealed: "complete",
  FAILED: "blocked",
  ROLLED_BACK: "blocked",
  CANCELLED: "blocked",
  DIAGNOSTIC_HOLD: "blocked",
} satisfies Record<AuthoritativeRouteStatus, JourneyState>;

function milestone(key: JourneyKey, label: string, state: JourneyState = "not-reached"): JourneyMilestone {
  return { key, label, state };
}

function orderedEvents(run: AuthoritativeRunStateDto): WorkflowEventDto[] {
  return [...run.workflow_events].sort((left, right) => left.sequence - right.sequence);
}

const GATE_EVIDENCE_EVENT_TYPES: Partial<Record<GateId, ReadonlySet<string>>> = {
  G05: new Set(["COMPATIBILITY_RESOLUTION_COMPLETED", "COMPATIBILITY_RESOLUTION_BLOCKED"]),
  G06: new Set(["MIGRATION_PLAN_CREATED", "STAGE_PLAN_CREATED", "PLANNING_AGENT_COMPLETED"]),
};

function latestGateState(events: WorkflowEventDto[], gateIds: GateId[]): Pick<JourneyMilestone, "state" | "evidenceEvent" | "evidenceEvents"> | null {
  const created = events
    .filter((event) => gateIds.some((gateId) => event.event_type === `${gateId}_CREATED`))
    .at(-1);
  if (!created) return null;

  const gateId = created.event_type.slice(0, 3) as GateId;
  const previousCreatedSequence = events
    .filter((event) => event.sequence < created.sequence && event.event_type === `${gateId}_CREATED`)
    .at(-1)?.sequence ?? 0;
  const supportingTypes = GATE_EVIDENCE_EVENT_TYPES[gateId];
  const supportingEvents = supportingTypes
    ? events.filter((event) => event.sequence > previousCreatedSequence && event.sequence < created.sequence && supportingTypes.has(event.event_type))
    : [];
  const terminal = events
    .filter((event) =>
      event.sequence > created.sequence
      && TERMINAL_SUFFIXES.some((suffix) => event.event_type === `${gateId}_${suffix}`),
    )
    .at(-1);

  const evidenceEvents = [...supportingEvents.map((event) => event.event_id), created.event_id];
  if (!terminal) return { state: "action-required", evidenceEvent: created.event_id, evidenceEvents };
  return {
    state: terminal.event_type.endsWith("_APPROVED") || terminal.event_type.endsWith("_APPROVED_WITH_RISK")
      ? "complete"
      : "blocked",
    evidenceEvent: terminal.event_id,
    evidenceEvents: [...evidenceEvents, terminal.event_id],
  };
}

function routeState(rawStatus: string): JourneyState {
  return Object.prototype.hasOwnProperty.call(ROUTE_STATUS_STATES, rawStatus)
    ? ROUTE_STATUS_STATES[rawStatus as AuthoritativeRouteStatus]
    : "unavailable";
}

function latestGateApproved(events: WorkflowEventDto[], gateId: "G09" | "G11" | "G12"): WorkflowEventDto | null {
  const created = events.filter((event) => event.event_type === `${gateId}_CREATED`).at(-1);
  if (!created) return null;
  return events
    .filter((event) => event.sequence > created.sequence && event.event_type === `${gateId}_APPROVED`)
    .at(-1) ?? null;
}

function finalValidationAccepted(events: WorkflowEventDto[]): WorkflowEventDto | null {
  return latestGateApproved(events, "G11")
    ?? (latestGateApproved(events, "G09") && latestGateApproved(events, "G12"));
}

function finalValidationPassed(transformation: TransformationProjection | null): boolean {
  if (!transformation) return false;
  return ["npm_ci", "build", "test"].every(
    (target) => transformation.validation_results[target]?.status === "PASSED",
  );
}

function sealedApplicableRoute(transformation: TransformationProjection | null, runId: string): boolean {
  return transformation?.run_id === runId
    && transformation.route_stages.length > 0
    && transformation.route_stages.every((stage) => stage.status === "sealed");
}

function applyExplicitRunCurrent(run: AuthoritativeRunStateDto, byKey: Map<JourneyKey, JourneyMilestone>): void {
  const key = run.status === "ANALYSIS_RUNNING" ? "discovery" : null;
  if (key && byKey.get(key)?.state === "not-reached") byKey.get(key)!.state = "current";
}

function stageLabel(sourceMajor: number, targetMajor: number): string {
  return `Angular ${sourceMajor} to ${targetMajor}`;
}

function materializedStages(transformation: TransformationProjection | null, runId: string): TransformationProjection["route_stages"] {
  return transformation?.run_id === runId ? transformation.route_stages : [];
}

function majorOf(version: string | null): number {
  const match = version?.match(/\d+/);
  return match ? Number(match[0]) : 0;
}

function transformationStageMilestones(
  transformation: TransformationProjection | null,
  runId: string,
  transformationStatus: TransformationLoadStatus,
  approvedRoute: ApprovedJourneyRoute | null,
): JourneyMilestone[] {
  const materialized = new Map(
    materializedStages(transformation, runId)
      .filter((stage) => stage.stage_id)
      .map((stage) => [stage.stage_id, stage]),
  );

  if (approvedRoute) {
    return approvedRoute.map((stage) => {
      const status = materialized.get(stage.stageId)?.status;
      return {
        key: stageJourneyKey(stage.stageId),
        label: stageLabel(stage.sourceMajor, stage.targetMajor),
        state: status ? routeState(status) : "not-reached",
        stageId: stage.stageId,
      };
    });
  }

  if (transformation?.run_id === runId && transformationStatus === "ready") {
    return transformation.route_stages
      .filter((stage) => stage.stage_id)
      .map((stage) => ({
        key: stageJourneyKey(stage.stage_id),
        label: stageLabel(majorOf(stage.source_version), majorOf(stage.target_version)),
        state: routeState(stage.status),
        stageId: stage.stage_id,
      }));
  }

  return [];
}

export function buildJourney(
  run: AuthoritativeRunStateDto,
  transformation: TransformationProjection | null,
  transformationStatus: TransformationLoadStatus,
  approvedRoute: ApprovedJourneyRoute | null = null,
): JourneyMilestone[] {
  const events = orderedEvents(run);
  const byKey = new Map<JourneyKey, JourneyMilestone>();
  for (const key of FIXED_JOURNEY_KEYS) {
    byKey.set(key, milestone(key, JOURNEY_LABELS[key]));
  }
  const runCreated = events.some((event) => event.event_type === "RUN_CREATED");
  const preflightEvidence = run.preflight_id.trim();

  for (const key of ["setup", "readiness", "g01"] as const) {
    const item = byKey.get(key)!;
    if (runCreated && preflightEvidence) {
      item.state = "complete";
      item.evidenceEvent = preflightEvidence;
    } else {
      item.state = "unavailable";
    }
  }

  const gateMilestones: Array<[FixedJourneyKey, GateId[]]> = [
    ["readiness", ["G02"]],
    ["baseline", ["G03"]],
    ["discovery", ["G04"]],
    ["feasibility", ["G05"]],
    ["plan", ["G06"]],
  ];
  for (const [key, gateIds] of gateMilestones) {
    const state = latestGateState(events, gateIds);
    if (state) Object.assign(byKey.get(key)!, state);
  }

  const planBlocked = byKey.get("plan")!.state === "blocked";
  const stageMilestones = planBlocked
    ? []
    : transformationStageMilestones(transformation, run.run_id, transformationStatus, approvedRoute);
  for (const stage of stageMilestones) byKey.set(stage.key, stage);

  const validationAcceptance = finalValidationAccepted(events);
  if (validationAcceptance && finalValidationPassed(transformation)) {
    Object.assign(byKey.get("validate")!, { state: "complete", evidenceEvent: validationAcceptance.event_id });
  }
  const stagedMigrationCompleted = events.find((event) => event.event_type === "STAGED_MIGRATION_COMPLETED");
  if (
    validationAcceptance
    && finalValidationPassed(transformation)
    && stagedMigrationCompleted
    && run.status === "COMPLETED"
    && sealedApplicableRoute(transformation, run.run_id)
  ) {
    Object.assign(byKey.get("complete")!, { state: "complete", evidenceEvent: stagedMigrationCompleted.event_id });
  }

  applyExplicitRunCurrent(run, byKey);
  return [
    ...PRE_TRANSFORMATION_KEYS.map((key) => byKey.get(key)!),
    ...stageMilestones,
    ...POST_TRANSFORMATION_KEYS.map((key) => byKey.get(key)!),
  ];
}