import { buildJourney, type JourneyKey } from "@/presentation/runJourney";
import { makeAuthoritativeRun, makeEvent } from "@/test/authoritativeFixtures";
import type { TransformationProjection } from "@/types/transformation";

function makeTransformation(
  overrides: Partial<TransformationProjection> = {},
): TransformationProjection {
  return {
    run_id: "run-fixture",
    continuation_id: "continuation-fixture",
    stage_id: "stage-18-19",
    status: "running",
    current_node: "stage_transformation",
    state_version: 40,
    stage_status: "running",
    source_version: "18.2.0",
    target_version: "19.0.0",
    checkpoint_kind: null,
    workspace_fingerprint: "sha256:workspace",
    active_gate: null,
    active_gate_package_checksum: null,
    active_command_id: null,
    active_command_status: null,
    active_prompt_id: null,
    active_prompt_checksum: null,
    active_prompt_text: null,
    active_prompt_options: [],
    active_prompt_explanation: null,
    repair_attempt_id: null,
    repair_attempt_number: null,
    repair_status: null,
    repair_risk_level: null,
    repair_proposal_checksum: null,
    repair_review_checksum: null,
    repair_proposal_id: null,
    repair_base_checksum: null,
    repair_safe_diff: null,
    repair_review: null,
    repair_rationale: [],
    repair_apply_checksum: null,
    repair_validation_checksum: null,
    workflow_step: "stage_transformation",
    active_command_phase: null,
    stage_start_fingerprint: "sha256:workspace",
    repair_contract: null,
    dependency_operation: null,
    completed_transition_phases: [],
    repair_verification: null,
    dependency_closure: null,
    validation_results: {},
    active_error: null,
    historical_diagnostics: [],
    route_stages: [],
    sealed_chain_hash: null,
    last_error_code: null,
    last_error_message: null,
    runtime_profile_binding: null,
    cancel_requested_at: null,
    ...overrides,
  };
}

function stateOf(
  journey: ReturnType<typeof buildJourney>,
  key: JourneyKey,
) {
  const milestone = journey.find((item) => item.key === key);
  expect(milestone, `missing journey milestone ${key}`).toBeDefined();
  return milestone!;
}

describe("buildJourney", () => {
  it("withholds preflight milestones when RUN_CREATED lacks a preflight binding", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({ preflight_id: "", workflow_events: [makeEvent("RUN_CREATED", 1)] }),
      null,
      "empty",
    );

    expect(stateOf(journey, "setup").state).toBe("unavailable");
    expect(stateOf(journey, "readiness").state).toBe("unavailable");
    expect(stateOf(journey, "g01").state).toBe("unavailable");
    expect(stateOf(journey, "baseline").state).not.toBe("complete");
  });

  it("uses the bound preflight as evidence that setup, readiness, and G01 completed", () => {
    const journey = buildJourney(makeAuthoritativeRun(), null, "empty");

    for (const key of ["setup", "readiness", "g01"] as const) {
      expect(stateOf(journey, key)).toMatchObject({
        state: "complete",
        evidenceEvent: "preflight-fixture",
      });
    }
  });

  it("does not invent a current milestone when no authoritative current fact exists", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({ status: "CREATED", phase_status: "not_started" }),
      null,
      "empty",
    );

    expect(stateOf(journey, "baseline").state).toBe("not-reached");
    expect(journey.some((item) => item.state === "current")).toBe(false);
  });

  it("marks Discovery current only from explicit ANALYSIS_RUNNING authority", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        status: "ANALYSIS_RUNNING",
        run_phase: "DISCOVERY_BASELINE",
        phase_status: "running",
      }),
      null,
      "empty",
    );

    expect(stateOf(journey, "baseline").state).toBe("not-reached");
    expect(stateOf(journey, "discovery").state).toBe("current");
  });

  it.each([
      ["G02", "readiness"],
    ["G03", "baseline"],
    ["G04", "discovery"],
    ["G05", "feasibility"],
    ["G06", "plan"],
  ] as const)("uses only the latest %s gate instance outcome", (gateId, milestoneKey) => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent(`${gateId}_CREATED`, 2, { event_id: `${gateId}-old-created` }),
          makeEvent(`${gateId}_APPROVED`, 3, { event_id: `${gateId}-old-approved` }),
          makeEvent(`${gateId}_CREATED`, 8, { event_id: `${gateId}-new-created` }),
          makeEvent(`${gateId}_REJECTED`, 7, { event_id: `${gateId}-out-of-order-rejected` }),
        ],
      }),
      null,
      "empty",
    );

    expect(stateOf(journey, milestoneKey)).toMatchObject({
      state: "action-required",
      evidenceEvent: `${gateId}-new-created`,
    });
  });

  it("marks feasibility action required for a durable pending G05 instance", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        workflow_events: [makeEvent("RUN_CREATED", 1), makeEvent("G05_CREATED", 2)],
      }),
      null,
      "empty",
    );

    expect(stateOf(journey, "feasibility")).toMatchObject({
      state: "action-required",
      evidenceEvent: "event-2-g05_created",
    });
  });

  it("blocks the plan on G06 rejection without claiming transformation progress", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G06_CREATED", 2),
          makeEvent("G06_REJECTED", 3),
        ],
      }),
      null,
      "empty",
    );

    expect(stateOf(journey, "plan").state).toBe("blocked");
    expect(stateOf(journey, "18-to-19").state).toBe("not-reached");
    expect(stateOf(journey, "19-to-20").state).toBe("not-reached");
    expect(stateOf(journey, "20-to-21").state).toBe("not-reached");
  });

  it("maps each route stage independently from authoritative transformation data", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        route_stages: [
          { stage_id: "stage-a", source_version: "18.2.0", target_version: "19.1.0", status: "PASSED" },
          { stage_id: "stage-b", source_version: "19", target_version: "20", status: "RUNNING" },
          { stage_id: "stage-c", source_version: "20.x", target_version: "21.x", status: "FAILED" },
        ],
      }),
      "ready",
    );

    expect(stateOf(journey, "18-to-19")).toMatchObject({ state: "complete", stageId: "stage-a" });
    expect(stateOf(journey, "19-to-20")).toMatchObject({ state: "current", stageId: "stage-b" });
    expect(stateOf(journey, "20-to-21")).toMatchObject({ state: "blocked", stageId: "stage-c" });
  });

  it.each([
    ["PENDING", "not-reached"],
    ["preparing", "current"],
    ["RUNNING", "current"],
    ["WAITING_APPROVAL", "action-required"],
    ["REPAIRING", "current"],
    ["PASSED", "complete"],
    ["passed_with_known_baseline_failures", "complete"],
    ["passed_with_manual_items", "complete"],
    ["sealed", "complete"],
    ["FAILED", "blocked"],
    ["ROLLED_BACK", "blocked"],
    ["CANCELLED", "blocked"],
    ["DIAGNOSTIC_HOLD", "blocked"],
  ] as const)("maps authoritative route status %s to %s", (status, expectedState) => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        route_stages: [
          { stage_id: `stage-${status}`, source_version: "18", target_version: "19", status },
        ],
      }),
      "ready",
    );

    expect(stateOf(journey, "18-to-19").state).toBe(expectedState);
  });

  it("keeps a sealed lookalike unavailable", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        route_stages: [
          { stage_id: "stage-sealed-candidate", source_version: "18", target_version: "19", status: "sealed_candidate" },
        ],
      }),
      "ready",
    );

    expect(stateOf(journey, "18-to-19").state).toBe("unavailable");
  });

  it("marks all route milestones unavailable when a ready projection has no route entries", () => {
    const journey = buildJourney(makeAuthoritativeRun(), makeTransformation({ route_stages: [] }), "ready");

    expect(stateOf(journey, "18-to-19").state).toBe("unavailable");
    expect(stateOf(journey, "19-to-20").state).toBe("unavailable");
    expect(stateOf(journey, "20-to-21").state).toBe("unavailable");
  });

  it("marks absent route milestones unavailable in a partial ready projection", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        route_stages: [
          { stage_id: "stage-18-19", source_version: "18", target_version: "19", status: "RUNNING" },
        ],
      }),
      "ready",
    );

    expect(stateOf(journey, "18-to-19").state).toBe("current");
    expect(stateOf(journey, "19-to-20").state).toBe("unavailable");
    expect(stateOf(journey, "20-to-21").state).toBe("unavailable");
  });

  it("marks route milestones unavailable when ready entries cannot map to the supported route", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        route_stages: [
          { stage_id: "stage-17-18", source_version: "17", target_version: "18", status: "RUNNING" },
        ],
      }),
      "ready",
    );

    expect(stateOf(journey, "18-to-19").state).toBe("unavailable");
    expect(stateOf(journey, "19-to-20").state).toBe("unavailable");
    expect(stateOf(journey, "20-to-21").state).toBe("unavailable");
  });

  it("marks missing transformation data unavailable when durable transformation evidence exists", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        workflow_events: [makeEvent("RUN_CREATED", 1), makeEvent("G07_CREATED", 2)],
      }),
      null,
      "failed",
    );

    expect(stateOf(journey, "18-to-19").state).toBe("unavailable");
    expect(stateOf(journey, "18-to-19").state).not.toBe("complete");
  });

  it("treats staged-migration completion as transformation evidence when projection data is missing", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        workflow_events: [makeEvent("RUN_CREATED", 1), makeEvent("STAGED_MIGRATION_COMPLETED", 2)],
      }),
      null,
      "empty",
    );

    expect(stateOf(journey, "18-to-19").state).toBe("unavailable");
  });

  it("projects a sealed completed 20-to-21 route from final validation and completion authority", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        status: "COMPLETED",
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G11_CREATED", 2),
          makeEvent("G11_APPROVED", 3),
          makeEvent("STAGED_MIGRATION_COMPLETED", 4),
        ],
      }),
      makeTransformation({
        route_stages: [
          { stage_id: "stage-20-21", source_version: "20.3.27", target_version: "21.2.19", status: "sealed" },
        ],
        validation_results: {
          npm_ci: { status: "PASSED", execution_id: "install", command_status: "succeeded" },
          build: { status: "PASSED", execution_id: "build", command_status: "succeeded" },
          test: { status: "PASSED", execution_id: "test", command_status: "succeeded" },
        },
      }),
      "ready",
    );

    expect(stateOf(journey, "18-to-19").state).toBe("unavailable");
    expect(stateOf(journey, "19-to-20").state).toBe("unavailable");
    expect(stateOf(journey, "20-to-21").state).toBe("complete");
    expect(stateOf(journey, "validate").state).toBe("complete");
    expect(stateOf(journey, "complete").state).toBe("complete");
  });

  it("does not complete final milestones when transformation validation has not passed", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        status: "COMPLETED",
        workflow_events: [makeEvent("G11_CREATED", 1), makeEvent("G11_APPROVED", 2), makeEvent("STAGED_MIGRATION_COMPLETED", 3)],
      }),
      makeTransformation({
        route_stages: [{ stage_id: "stage-20-21", source_version: "20", target_version: "21", status: "sealed" }],
        validation_results: { npm_ci: { status: "PASSED", execution_id: null, command_status: "succeeded" } },
      }),
      "ready",
    );

    expect(stateOf(journey, "20-to-21").state).toBe("complete");
    expect(stateOf(journey, "validate").state).not.toBe("complete");
    expect(stateOf(journey, "complete").state).not.toBe("complete");
  });

  it("keeps Complete pending until the validated route is sealed and terminal", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({ workflow_events: [makeEvent("G11_CREATED", 1), makeEvent("G11_APPROVED", 2)] }),
      makeTransformation({
        route_stages: [{ stage_id: "stage-20-21", source_version: "20", target_version: "21", status: "PASSED" }],
        validation_results: {
          npm_ci: { status: "PASSED", execution_id: null, command_status: "succeeded" },
          build: { status: "PASSED", execution_id: null, command_status: "succeeded" },
          test: { status: "PASSED", execution_id: null, command_status: "succeeded" },
        },
      }),
      "ready",
    );

    expect(stateOf(journey, "validate").state).toBe("complete");
    expect(stateOf(journey, "complete").state).not.toBe("complete");
  });

  it("counts every applicable transformation in a completed 18-to-21 route", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        status: "COMPLETED",
        workflow_events: [makeEvent("G11_CREATED", 1), makeEvent("G11_APPROVED", 2), makeEvent("STAGED_MIGRATION_COMPLETED", 3)],
      }),
      makeTransformation({
        route_stages: [
          { stage_id: "stage-18-19", source_version: "18", target_version: "19", status: "sealed" },
          { stage_id: "stage-19-20", source_version: "19", target_version: "20", status: "sealed" },
          { stage_id: "stage-20-21", source_version: "20", target_version: "21", status: "sealed" },
        ],
        validation_results: {
          npm_ci: { status: "PASSED", execution_id: null, command_status: "succeeded" },
          build: { status: "PASSED", execution_id: null, command_status: "succeeded" },
          test: { status: "PASSED", execution_id: null, command_status: "succeeded" },
        },
      }),
      "ready",
    );

    for (const key of ["18-to-19", "19-to-20", "20-to-21", "validate", "complete"] as const) {
      expect(stateOf(journey, key).state).toBe("complete");
    }
  });
});
