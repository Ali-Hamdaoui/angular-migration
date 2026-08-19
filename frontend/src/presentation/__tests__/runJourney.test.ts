import {
  buildJourney,
  isStageJourneyKey,
  type ApprovedJourneyRoute,
  type JourneyKey,
} from "@/presentation/runJourney";
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

function routeOf(startMajor: number, endMajor: number): ApprovedJourneyRoute {
  const stages: ApprovedJourneyRoute = [];
  for (let major = startMajor; major < endMajor; major += 1) {
    stages.push({
      stageId: `stage-${major}-${major + 1}`,
      sourceMajor: major,
      targetMajor: major + 1,
    });
  }
  return stages;
}

function stateOf(
  journey: ReturnType<typeof buildJourney>,
  key: JourneyKey,
) {
  const milestone = journey.find((item) => item.key === key);
  expect(milestone, `missing journey milestone ${key}`).toBeDefined();
  return milestone!;
}

function transformationMilestones(journey: ReturnType<typeof buildJourney>) {
  return journey.filter((item) => isStageJourneyKey(item.key));
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

  it("blocks the plan on G06 rejection without inventing transformation milestones", () => {
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
      routeOf(11, 21),
    );

    expect(stateOf(journey, "plan").state).toBe("blocked");
    expect(transformationMilestones(journey)).toHaveLength(0);
  });

  it.each([
    [11, 21, 10, "stage:stage-11-12", "Angular 11 to 12", "stage:stage-20-21", "Angular 20 to 21"],
    [17, 21, 4, "stage:stage-17-18", "Angular 17 to 18", "stage:stage-20-21", "Angular 20 to 21"],
    [18, 21, 3, "stage:stage-18-19", "Angular 18 to 19", "stage:stage-20-21", "Angular 20 to 21"],
  ] as const)(
    "renders the complete approved %s-to-21 route as %s transformation milestones from one code path",
    (startMajor, endMajor, expectedCount, firstKey, firstLabel, lastKey, lastLabel) => {
      const journey = buildJourney(
        makeAuthoritativeRun(),
        makeTransformation(),
        "ready",
        routeOf(startMajor, endMajor),
      );

      const milestones = transformationMilestones(journey);
      expect(milestones).toHaveLength(expectedCount);
      expect(milestones[0]).toMatchObject({ key: firstKey, label: firstLabel, state: "not-reached" });
      expect(milestones.at(-1)).toMatchObject({ key: lastKey, label: lastLabel, state: "not-reached" });
      expect(milestones.every((item) => isStageJourneyKey(item.key))).toBe(true);
    },
  );

  it("renders the persisted 11-to-21 plan route as ten planned transformation milestones before any transformation materialization", () => {
    const route: ApprovedJourneyRoute = [
      { stageId: "angular-11-to-12--38e936ede40ca28c", sourceMajor: 11, targetMajor: 12 },
      { stageId: "angular-12-to-13--d8117f08b24caed0", sourceMajor: 12, targetMajor: 13 },
      { stageId: "angular-13-to-14--b9066112bb2c2cb8", sourceMajor: 13, targetMajor: 14 },
      { stageId: "angular-14-to-15--e80e030bc9108e80", sourceMajor: 14, targetMajor: 15 },
      { stageId: "angular-15-to-16--46af0d34c4b5f108", sourceMajor: 15, targetMajor: 16 },
      { stageId: "angular-16-to-17--c4061946ab968291", sourceMajor: 16, targetMajor: 17 },
      { stageId: "angular-17-to-18--86db4495eb1f9866", sourceMajor: 17, targetMajor: 18 },
      { stageId: "angular-18-to-19--e417522667652d0a", sourceMajor: 18, targetMajor: 19 },
      { stageId: "angular-19-to-20--d70ff163a0a918fb", sourceMajor: 19, targetMajor: 20 },
      { stageId: "angular-20-to-21--9e3a0703f778e629", sourceMajor: 20, targetMajor: 21 },
    ];
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation(),
      "disabled",
      route,
    );

    const milestones = transformationMilestones(journey);
    expect(milestones).toHaveLength(10);
    expect(milestones[0]).toMatchObject({
      key: "stage:angular-11-to-12--38e936ede40ca28c",
      label: "Angular 11 to 12",
      state: "not-reached",
      stageId: "angular-11-to-12--38e936ede40ca28c",
    });
    expect(milestones.at(-1)).toMatchObject({ label: "Angular 20 to 21", state: "not-reached" });
    expect(milestones.every((item) => item.state === "not-reached")).toBe(true);
  });

  it("orders every dynamic transformation milestone after plan and before validate", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation(),
      "ready",
      routeOf(12, 21),
    );

    expect(journey.map((item) => item.key)).toEqual([
      "setup",
      "readiness",
      "g01",
      "baseline",
      "discovery",
      "feasibility",
      "plan",
      "stage:stage-12-13",
      "stage:stage-13-14",
      "stage:stage-14-15",
      "stage:stage-15-16",
      "stage:stage-16-17",
      "stage:stage-17-18",
      "stage:stage-18-19",
      "stage:stage-19-20",
      "stage:stage-20-21",
      "validate",
      "complete",
    ]);
  });

  it("overlays sealed, current, and planned states as route stages materialize", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        stage_id: "stage-19-20",
        route_stages: [
          { stage_id: "stage-18-19", source_version: "18", target_version: "19", status: "sealed" },
          { stage_id: "stage-19-20", source_version: "19", target_version: "20", status: "RUNNING" },
        ],
      }),
      "ready",
      routeOf(18, 21),
    );

    expect(stateOf(journey, "stage:stage-18-19")).toMatchObject({ state: "complete", stageId: "stage-18-19" });
    expect(stateOf(journey, "stage:stage-19-20")).toMatchObject({ state: "current", stageId: "stage-19-20" });
    expect(stateOf(journey, "stage:stage-20-21")).toMatchObject({ state: "not-reached", stageId: "stage-20-21" });
  });

  it("attaches the active backend stage_id to its journey milestone", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        stage_id: "stage-16-17",
        route_stages: [
          { stage_id: "stage-15-16", source_version: "15", target_version: "16", status: "sealed" },
          { stage_id: "stage-16-17", source_version: "16", target_version: "17", status: "RUNNING" },
        ],
      }),
      "ready",
      routeOf(15, 21),
    );

    expect(stateOf(journey, "stage:stage-16-17").stageId).toBe("stage-16-17");
  });

  it("uses stage_id-derived milestones from materialized stages when the approved route is unavailable", () => {
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

    expect(stateOf(journey, "stage:stage-a")).toMatchObject({ state: "complete", stageId: "stage-a" });
    expect(stateOf(journey, "stage:stage-b")).toMatchObject({ state: "current", stageId: "stage-b" });
    expect(stateOf(journey, "stage:stage-c")).toMatchObject({ state: "blocked", stageId: "stage-c" });
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

    expect(stateOf(journey, `stage:stage-${status}`).state).toBe(expectedState);
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

    expect(stateOf(journey, "stage:stage-sealed-candidate").state).toBe("unavailable");
  });

  it("renders no transformation milestones without route authority", () => {
    const journey = buildJourney(makeAuthoritativeRun(), makeTransformation({ route_stages: [] }), "ready");

    expect(transformationMilestones(journey)).toHaveLength(0);
  });

  it("renders only the materialized stage without an approved route", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        route_stages: [
          { stage_id: "stage-18-19", source_version: "18", target_version: "19", status: "RUNNING" },
        ],
      }),
      "ready",
    );

    expect(stateOf(journey, "stage:stage-18-19").state).toBe("current");
    expect(transformationMilestones(journey)).toHaveLength(1);
  });

  it("accepts any backend stage_id without a supported-route mapping", () => {
    const journey = buildJourney(
      makeAuthoritativeRun(),
      makeTransformation({
        route_stages: [
          { stage_id: "stage-17-18", source_version: "17", target_version: "18", status: "RUNNING" },
        ],
      }),
      "ready",
    );

    expect(stateOf(journey, "stage:stage-17-18").state).toBe("current");
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
      routeOf(18, 21),
    );

    expect(stateOf(journey, "stage:stage-18-19").state).toBe("not-reached");
    expect(stateOf(journey, "stage:stage-19-20").state).toBe("not-reached");
    expect(stateOf(journey, "stage:stage-20-21").state).toBe("complete");
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
      routeOf(18, 21),
    );

    expect(stateOf(journey, "stage:stage-20-21").state).toBe("complete");
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
      routeOf(18, 21),
    );

    expect(stateOf(journey, "validate").state).toBe("complete");
    expect(stateOf(journey, "complete").state).not.toBe("complete");
  });

  it("counts every applicable transformation in a completed 11-to-21 route", () => {
    const journey = buildJourney(
      makeAuthoritativeRun({
        status: "COMPLETED",
        workflow_events: [makeEvent("G11_CREATED", 1), makeEvent("G11_APPROVED", 2), makeEvent("STAGED_MIGRATION_COMPLETED", 3)],
      }),
      makeTransformation({
        route_stages: routeOf(11, 21).map((stage) => ({
          stage_id: stage.stageId,
          source_version: String(stage.sourceMajor),
          target_version: String(stage.targetMajor),
          status: "sealed",
        })),
        validation_results: {
          npm_ci: { status: "PASSED", execution_id: null, command_status: "succeeded" },
          build: { status: "PASSED", execution_id: null, command_status: "succeeded" },
          test: { status: "PASSED", execution_id: null, command_status: "succeeded" },
        },
      }),
      "ready",
      routeOf(11, 21),
    );

    expect(transformationMilestones(journey)).toHaveLength(10);
    for (const milestone of transformationMilestones(journey)) {
      expect(milestone.state).toBe("complete");
    }
    expect(stateOf(journey, "validate").state).toBe("complete");
    expect(stateOf(journey, "complete").state).toBe("complete");
  });
});