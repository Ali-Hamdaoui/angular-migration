import type { AuthoritativeRunStateDto, StageStatus, WorkflowEventDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";
import type { GateId } from "@/presentation/gates";

export type JourneyKey =
  | "setup"
  | "readiness"
  | "g01"
  | "baseline"
  | "discovery"
  | "feasibility"
  | "plan"
  | "18-to-19"
  | "19-to-20"
  | "20-to-21"
  | "validate"
  | "complete";

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

const JOURNEY_LABELS: Record<JourneyKey, string> = {
  setup: "Setup",
  readiness: "Readiness",
  g01: "Production readiness",
  baseline: "Baseline",
  discovery: "Discovery",
  feasibility: "Feasibility",
  plan: "Migration plan",
  "18-to-19": "Angular 18 to 19",
  "19-to-20": "Angular 19 to 20",
  "20-to-21": "Angular 20 to 21",
  validate: "Validate",
  complete: "Complete",
};

const JOURNEY_ORDER = Object.keys(JOURNEY_LABELS) as JourneyKey[];
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

function milestone(key: JourneyKey, state: JourneyState = "not-reached"): JourneyMilestone {
  return { key, label: JOURNEY_LABELS[key], state };
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

function major(version: string | null): number | null {
  const match = version?.match(/\d+/);
  return match ? Number(match[0]) : null;
}

function routeKey(source: string | null, target: string | null): JourneyKey | null {
  const route = `${major(source)}-${major(target)}`;
  if (route === "18-19") return "18-to-19";
  if (route === "19-20") return "19-to-20";
  if (route === "20-21") return "20-to-21";
  return null;
}

function routeState(rawStatus: string): JourneyState {
  return Object.prototype.hasOwnProperty.call(ROUTE_STATUS_STATES, rawStatus)
    ? ROUTE_STATUS_STATES[rawStatus as AuthoritativeRouteStatus]
    : "unavailable";
}

function hasTransformationEvidence(events: WorkflowEventDto[]): boolean {
  return events.some((event) => /^(G(?:0[7-9]|1[0-2])_|TRANSFORMATION_|STAGE(?:D)?_|FINAL_TARGET_|CLI_|VERSION_|REPAIR_)/.test(event.event_type));
}

function applyExplicitRunCurrent(run: AuthoritativeRunStateDto, byKey: Map<JourneyKey, JourneyMilestone>): void {
  const key = run.status === "ANALYSIS_RUNNING" ? "discovery" : null;
  if (key && byKey.get(key)?.state === "not-reached") byKey.get(key)!.state = "current";
}

export function buildJourney(
  run: AuthoritativeRunStateDto,
  transformation: TransformationProjection | null,
  transformationStatus: TransformationLoadStatus,
): JourneyMilestone[] {
  const events = orderedEvents(run);
  const byKey = new Map(JOURNEY_ORDER.map((key) => [key, milestone(key)]));
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

  const gateMilestones: Array<[JourneyKey, GateId[]]> = [
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

  const routeKeys: JourneyKey[] = ["18-to-19", "19-to-20", "20-to-21"];
  const planBlocked = byKey.get("plan")!.state === "blocked";
  if (!planBlocked) {
    if (transformation && transformation.run_id === run.run_id && transformationStatus === "ready") {
      for (const key of routeKeys) byKey.get(key)!.state = "unavailable";
      for (const stage of transformation.route_stages) {
        const key = routeKey(stage.source_version, stage.target_version);
        if (!key) continue;
        Object.assign(byKey.get(key)!, { state: routeState(stage.status), stageId: stage.stage_id });
      }
    } else if (
      hasTransformationEvidence(events)
      || (transformation != null && transformation.run_id !== run.run_id)
      || (transformationStatus === "failed" && events.some((event) => event.event_type === "STAGED_MIGRATION_COMPLETED"))
    ) {
      for (const key of routeKeys) byKey.get(key)!.state = "unavailable";
    }
  }

  const stagedMigrationCompleted = events.find((event) => event.event_type === "STAGED_MIGRATION_COMPLETED");
  const finalTargetVerified = events.find((event) => event.event_type === "FINAL_TARGET_VERIFIED");
  if (finalTargetVerified) {
    Object.assign(byKey.get("validate")!, { state: "complete", evidenceEvent: finalTargetVerified.event_id });
  }
  if (stagedMigrationCompleted && finalTargetVerified) {
    Object.assign(byKey.get("complete")!, { state: "complete", evidenceEvent: stagedMigrationCompleted.event_id });
  }

  applyExplicitRunCurrent(run, byKey);
  return JOURNEY_ORDER.map((key) => byKey.get(key)!);
}
