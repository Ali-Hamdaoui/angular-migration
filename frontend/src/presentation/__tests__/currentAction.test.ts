import {
  buildRunWorkspaceProjection,
  selectCurrentAction,
} from "@/presentation/currentAction";
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
    state_version: 99,
    stage_status: "running",
    source_version: "18",
    target_version: "19",
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

describe("selectCurrentAction", () => {
  it("attributes G02 review to the typed readiness journey stage", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({
        state_version: 3,
        workflow_events: [
          makeEvent("G02_CREATED", 1, {
            payload: {
              gate_id: "G02",
              package_checksum: "sha256:g02",
              expected_state_version: 3,
              permitted_decisions: ["approved", "rejected"],
            },
          }),
        ],
      }),
      null,
      "disabled",
      "open",
    );

    expect(action).toMatchObject({ gateId: "G02", stageKey: "readiness" });
  });

  it("selects a backend-valid pending human gate before transformation and run blockers", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({ status: "FAILED", phase_status: "failed" }),
      makeTransformation({
        status: "waiting_gate",
        active_gate: "G11",
        active_gate_package_checksum: "sha256:g11",
        active_error: { code: "BLOCKED", message: "blocked" },
      }),
      "ready",
      "open",
    );

    expect(action).toMatchObject({
      kind: "gate",
      gateId: "G11",
      title: "Repair validation acceptance required",
      section: "pipeline",
      stageKey: "18-to-19",
    });
  });

  it.each([
    ["missing", null, null],
    ["unsupported", "17", "18"],
  ] as const)("omits stage attribution for a %s transformation route", (_case, sourceVersion, targetVersion) => {
    const action = selectCurrentAction(
      makeAuthoritativeRun(),
      makeTransformation({
        status: "waiting_gate",
        active_gate: "G07",
        active_gate_package_checksum: "sha256:g07",
        source_version: sourceVersion,
        target_version: targetVersion,
      }),
      "ready",
      "open",
    );

    expect(action).toMatchObject({ kind: "gate", gateId: "G07" });
    expect(action).not.toHaveProperty("stageKey");
  });

  it.each([
    [
      "blocked",
      { status: "blocked", active_error: { code: "POLICY_BLOCKED", message: "Policy blocked the stage." } },
      "Transformation blocked",
      "blocked",
    ],
    [
      "waiting gate without bindings",
      { status: "waiting_gate", active_gate: "G08", active_gate_package_checksum: null },
      "Transformation gate bindings unavailable",
      "unavailable",
    ],
    [
      "waiting prompt",
      { status: "waiting_prompt", active_prompt_id: "prompt-1", active_prompt_checksum: "sha256:prompt", active_prompt_text: "Choose a migration option" },
      "Command input required",
      "blocked",
    ],
    [
      "active command",
      { status: "running", active_command_id: "command-1", active_command_status: "running" },
      "Migration command running",
      "running",
    ],
  ] as const)("selects transformation %s before a run failure", (_case, overrides, title, kind) => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({ status: "FAILED", phase_status: "failed" }),
      makeTransformation(overrides),
      "ready",
      "open",
    );

    expect(action).toMatchObject({ title, kind, section: "pipeline" });
  });

  it.each(["unblocked", "failed_over"])("does not infer a blocker from unknown transformation status %s", (status) => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({ status: "CREATED", phase_status: "not_started", workflow_events: [] }),
      makeTransformation({ status, stage_status: "RUNNING" }),
      "ready",
      "open",
    );

    expect(action).toMatchObject({ kind: "unavailable", title: "Current action unavailable" });
  });

  it.each([
    ["explicit failure", { status: "FAILED" as const, phase_status: "failed", approval_status: "approved" as const }, "Run failed"],
    ["pending approval", { status: "WAITING_PLAN_APPROVAL" as const, phase_status: "waiting_approval", approval_status: "pending" as const }, "Run approval required"],
  ])("selects a run %s before verified completion", (_case, overrides, title) => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({
        ...overrides,
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("STAGED_MIGRATION_COMPLETED", 2),
          makeEvent("FINAL_TARGET_VERIFIED", 3),
        ],
      }),
      null,
      "empty",
      "open",
    );

    expect(action).toMatchObject({ kind: "blocked", title });
  });

  it("selects active run work before contradictory completion evidence", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({
        status: "ANALYSIS_RUNNING",
        phase_status: "running",
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("STAGED_MIGRATION_COMPLETED", 2),
          makeEvent("FINAL_TARGET_VERIFIED", 3),
        ],
      }),
      null,
      "empty",
      "open",
    );

    expect(action).toMatchObject({ kind: "running", title: "Analysis running" });
  });

  it("selects completion only when final durable verification exists", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({
        status: "COMPLETED",
        phase_status: "completed",
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("STAGED_MIGRATION_COMPLETED", 2),
          makeEvent("FINAL_TARGET_VERIFIED", 3),
        ],
      }),
      null,
      "empty",
      "open",
    );

    expect(action).toMatchObject({ kind: "complete", title: "Migration verified complete" });
  });

  it("fails closed when no current authoritative fact is available", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({
        status: "CREATED",
        phase_status: "not_started",
        preflight_id: "",
        workflow_events: [],
      }),
      null,
      "empty",
      "open",
    );

    expect(action).toMatchObject({ kind: "unavailable", title: "Current action unavailable" });
  });

  it("does not compare projection-local state versions", () => {
    const actionForDifferentProjectionVersions = selectCurrentAction(
      makeAuthoritativeRun({ state_version: 2 }),
      makeTransformation({ state_version: 987, active_command_id: "command-1", active_command_status: "running" }),
      "ready",
      "open",
    );

    expect(actionForDifferentProjectionVersions.rawSource).not.toContain("mismatch");
    expect(actionForDifferentProjectionVersions.title).toBe("Migration command running");
  });

  it.each(["recovering", "failed"] as const)("withholds decision controls while the connection is %s", (connection) => {
    const actionDuringRecovery = selectCurrentAction(
      makeAuthoritativeRun(),
      makeTransformation({
        status: "waiting_gate",
        active_gate: "G07",
        active_gate_package_checksum: "sha256:g07",
      }),
      "ready",
      connection,
    );

    expect(actionDuringRecovery.title).toBe("Authoritative state is refreshing");
    expect(actionDuringRecovery).toMatchObject({ kind: "unavailable", section: "diagnostics" });
  });

  it("does not claim a permitted run gate decision without backend bindings", () => {
    const actionWithoutGateBindings = selectCurrentAction(
      makeAuthoritativeRun({
        status: "WAITING_PLAN_APPROVAL",
        approval_status: "pending",
        workflow_events: [makeEvent("RUN_CREATED", 1), makeEvent("G06_CREATED", 2)],
      }),
      null,
      "empty",
      "open",
    );

    expect(actionWithoutGateBindings.kind).not.toBe("gate");
    expect(actionWithoutGateBindings.title).toBe("Run approval required");
  });

  it("does not accept a preflight gate identifier from a transformation binding", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun(),
      makeTransformation({
        status: "waiting_gate",
        active_gate: "G01",
        active_gate_package_checksum: "sha256:g01",
      }),
      "ready",
      "open",
    );

    expect(action.kind).not.toBe("gate");
    expect(action.title).toBe("Transformation gate bindings unavailable");
  });

  it("accepts an exact run gate binding package", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({
        state_version: 7,
        status: "WAITING_PLAN_APPROVAL",
        approval_status: "pending",
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G06_CREATED", 2, {
            payload: {
              gate_id: "G06",
              package_checksum: "sha256:g06",
              expected_state_version: 7,
              permitted_decisions: ["approved", "modification_requested", "rejected"],
              evidence_ids: ["plan-artifact"],
            },
          }),
        ],
      }),
      null,
      "empty",
      "open",
    );

    expect(action).toMatchObject({
      kind: "gate",
      gateId: "G06",
      title: "Migration plan acceptance required",
      evidenceIds: ["event-2-g06_created", "plan-artifact"],
    });
  });

  it("withholds a run gate action when its expected state version is stale", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun({
        state_version: 8,
        status: "WAITING_PLAN_APPROVAL",
        approval_status: "pending",
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G06_CREATED", 2, {
            payload: {
              gate_id: "G06",
              package_checksum: "sha256:g06",
              expected_state_version: 7,
              permitted_decisions: ["approved", "rejected"],
            },
          }),
        ],
      }),
      null,
      "empty",
      "open",
    );

    expect(action.kind).not.toBe("gate");
    expect(action.title).toBe("Run approval required");
  });

  it("routes incompatible run identifiers to authoritative refresh diagnostics", () => {
    const action = selectCurrentAction(
      makeAuthoritativeRun(),
      makeTransformation({ run_id: "another-run" }),
      "ready",
      "open",
    );

    expect(action).toMatchObject({
      kind: "unavailable",
      title: "Authoritative state is refreshing",
      section: "diagnostics",
    });
  });
});

describe("buildRunWorkspaceProjection", () => {
  it.each([
    ["pending", [makeEvent("G02_CREATED", 2)], "action-required"],
    ["approved", [makeEvent("G02_CREATED", 2), makeEvent("G02_APPROVED", 3)], "complete"],
  ] as const)("attributes a %s G02 package to Readiness without advancing Baseline", (_case, gateEvents, readinessState) => {
    const projection = buildRunWorkspaceProjection(
      makeAuthoritativeRun({ workflow_events: [makeEvent("RUN_CREATED", 1), ...gateEvents] }),
      null,
      "empty",
      "open",
    );

    expect(projection.journey.find((item) => item.key === "readiness")?.state).toBe(readinessState);
    expect(projection.journey.find((item) => item.key === "baseline")?.state).toBe("not-reached");
  });

  it.each([
    ["pending", makeEvent("G03_CREATED", 4), "action-required"],
    ["rejected", makeEvent("G03_REJECTED", 5), "blocked"],
  ] as const)("attributes a %s G03 package only to Baseline", (_case, lastGateEvent, baselineState) => {
    const projection = buildRunWorkspaceProjection(
      makeAuthoritativeRun({
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G02_CREATED", 2),
          makeEvent("G02_APPROVED", 3),
          makeEvent("G03_CREATED", 4),
          ...(lastGateEvent.sequence === 4 ? [] : [lastGateEvent]),
        ],
      }),
      null,
      "empty",
      "open",
    );

    expect(projection.journey.find((item) => item.key === "readiness")?.state).toBe("complete");
    expect(projection.journey.find((item) => item.key === "baseline")?.state).toBe(baselineState);
  });

  it("withholds action navigation while same-run transformation authority is refreshing", () => {
    const projection = buildRunWorkspaceProjection(
      makeAuthoritativeRun(),
      makeTransformation({
        status: "blocked",
        active_error: { code: "POLICY_BLOCKED", message: "Policy blocked the stage." },
      }),
      "ready",
      "open",
      "refreshing",
    );

    expect(projection.currentAction).toMatchObject({
      title: "Authoritative state is refreshing",
      authority: { freshness: "refreshing", navigation: "withheld" },
    });
  });

  it("composes journey summaries from the same pure authoritative inputs", () => {
    const projection = buildRunWorkspaceProjection(
      makeAuthoritativeRun({
        status: "ANALYSIS_RUNNING",
        run_phase: "DISCOVERY_BASELINE",
        phase_status: "running",
      }),
      null,
      "empty",
      "open",
    );

    expect(projection.now).toBe("Analysis running");
    expect(projection.completed).toBe("Setup, Readiness, Production readiness");
    expect(projection.next).toBe("Discovery");
    expect(projection.journey).toHaveLength(12);
  });

  it("keeps a rejected G06 blocker as next instead of advancing to transformation", () => {
    const projection = buildRunWorkspaceProjection(
      makeAuthoritativeRun({
        status: "WAITING_PLAN_APPROVAL",
        phase_status: "blocked",
        approval_status: "rejected",
        workflow_events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G06_CREATED", 2),
          makeEvent("G06_REJECTED", 3),
        ],
      }),
      null,
      "empty",
      "open",
    );

    expect(projection.next).toBe("Migration plan");
    expect(projection.journey.find((item) => item.key === "18-to-19")?.state).toBe("not-reached");
  });

  it("withholds next when no authoritative current, action, or blocker fact exists", () => {
    const projection = buildRunWorkspaceProjection(
      makeAuthoritativeRun({
        status: "CREATED",
        phase_status: "not_started",
        preflight_id: "",
        workflow_events: [],
      }),
      null,
      "empty",
      "open",
    );

    expect(projection.currentAction.kind).toBe("unavailable");
    expect(projection.next).toBe("Next milestone unavailable");
  });
});
