import type { AuthoritativeRunStateDto, WorkflowEventDto } from "@/types/generated/api";
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
  stageId?: string;
}

export type TransformationLoadStatus = "disabled" | "loading" | "ready" | "empty" | "failed";

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

function milestone(key: JourneyKey, state: JourneyState = "not-reached"): JourneyMilestone {
  return { key, label: JOURNEY_LABELS[key], state };
}

function orderedEvents(run: AuthoritativeRunStateDto): WorkflowEventDto[] {
  return [...run.workflow_events].sort((left, right) => left.sequence - right.sequence);
}

function latestGateState(events: WorkflowEventDto[], gateIds: GateId[]): Pick<JourneyMilestone, "state" | "evidenceEvent"> | null {
  const created = events
    .filter((event) => gateIds.some((gateId) => event.event_type === `${gateId}_CREATED`))
    .at(-1);
  if (!created) return null;

  const gateId = created.event_type.slice(0, 3) as GateId;
  const terminal = events
    .filter((event) =>
      event.sequence > created.sequence
      && TERMINAL_SUFFIXES.some((suffix) => event.event_type === `${gateId}_${suffix}`),
    )
    .at(-1);

  if (!terminal) return { state: "action-required", evidenceEvent: created.event_id };
  return {
    state: terminal.event_type.endsWith("_APPROVED") || terminal.event_type.endsWith("_APPROVED_WITH_RISK")
      ? "complete"
      : "blocked",
    evidenceEvent: terminal.event_id,
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
  const status = rawStatus.trim().toLowerCase();
  if (["completed", "complete", "passed", "sealed", "succeeded"].includes(status)) return "complete";
  if (["running", "active", "in_progress", "preparing"].includes(status)) return "current";
  if (status.startsWith("waiting") || status === "action_required") return "action-required";
  if (["blocked", "failed", "cancelled", "rolled_back"].includes(status)) return "blocked";
  if (["pending", "not_started", "queued"].includes(status)) return "not-reached";
  return "unavailable";
}

function hasTransformationEvidence(events: WorkflowEventDto[]): boolean {
  return events.some((event) => /^(G(?:0[7-9]|1[0-2])_|TRANSFORMATION_|STAGE(?:D)?_|FINAL_TARGET_|CLI_|VERSION_|REPAIR_)/.test(event.event_type));
}

function applyCurrentMarker(journey: JourneyMilestone[]): void {
  if (journey.some((item) => item.state === "current" || item.state === "action-required" || item.state === "blocked")) return;
  const firstNotReached = journey.find((item) => item.state === "not-reached");
  if (firstNotReached) firstNotReached.state = "current";
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
    ["baseline", ["G02", "G03"]],
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

  const journey = JOURNEY_ORDER.map((key) => byKey.get(key)!);
  applyCurrentMarker(journey);
  return journey;
}
