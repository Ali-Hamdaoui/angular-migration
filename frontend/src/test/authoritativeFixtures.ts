import type {
  ArtifactRefDto,
  AuthoritativeRunStateDto,
  WorkflowEventDto,
} from "@/types/generated/api";

export function makeEvent(
  eventType: string,
  sequence: number,
  overrides: Partial<WorkflowEventDto> = {},
): WorkflowEventDto {
  return {
    event_id: `event-${sequence}-${eventType.toLowerCase()}`,
    run_id: "run-fixture",
    stage_id: null,
    event_type: eventType,
    occurred_at: `2026-08-09T10:${String(sequence).padStart(2, "0")}:00Z`,
    sequence,
    payload: {},
    ...overrides,
  };
}

export function makeArtifact(
  overrides: Partial<ArtifactRefDto> = {},
): ArtifactRefDto {
  return {
    artifact_id: "artifact-fixture",
    run_id: "run-fixture",
    stage_id: null,
    artifact_type: "json",
    relative_path: "00_job_setup/fixture.json",
    created_at: "2026-08-09T10:00:00Z",
    checksum: "sha256:fixture",
    ...overrides,
  };
}

export function makeAuthoritativeRun(
  overrides: Partial<AuthoritativeRunStateDto> = {},
): AuthoritativeRunStateDto {
  return {
    run_id: "run-fixture",
    status: "CREATED",
    run_phase: "PREFLIGHT_SNAPSHOT",
    phase_status: "running",
    approval_status: "approved",
    repair_status: "not_required",
    state_version: 1,
    preflight_id: "preflight-fixture",
    source_path: "C:/external/source",
    target_output_path: "C:/external/target/source-angular-21",
    graph_thread_id: "source-intake-run-fixture",
    created_at: "2026-08-09T10:00:00Z",
    updated_at: "2026-08-09T10:00:00Z",
    artifacts: [],
    workflow_events: [makeEvent("RUN_CREATED", 1)],
    ...overrides,
  };
}

export const analysisPrerequisites = [
  makeEvent("G03_APPROVED", 2),
  makeEvent("DISCOVERY_COMPLETED", 3),
  makeEvent("PARITY_BASELINE_COMPLETED", 4),
];

export const feasibilityPrerequisites = [
  ...analysisPrerequisites,
  makeEvent("G04_APPROVED", 5),
];
