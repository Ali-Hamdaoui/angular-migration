import { renderHook, waitFor } from "@testing-library/react";
import { ApiClientError } from "@/api/client";
import { getFeasibility } from "@/api/compatibility";
import { getPlan } from "@/api/plans";
import { buildApprovedJourneyRoute, useApprovedJourneyRoute } from "@/hooks/useApprovedJourneyRoute";
import type { FeasibilityResponse } from "@/types/compatibility";
import type { PlanResponse } from "@/types/planning";

vi.mock("@/api/plans", () => ({ getPlan: vi.fn() }));
vi.mock("@/api/compatibility", () => ({ getFeasibility: vi.fn() }));

function feasibility(routeIds: string[]): FeasibilityResponse {
  return {
    run_id: "run-fixture",
    resolution_id: "resolution-1",
    status: "feasible",
    source_exact: "17.3.0",
    source_family: "angular-17.x",
    target_family: "angular-21.x",
    support_level: "historical_experimental",
    route: routeIds.map((stageId, index) => {
      const sourceMajor = 17 + index;
      return {
        stage_id: stageId,
        source_family: `angular-${sourceMajor}.x`,
        target_family: `angular-${sourceMajor + 1}.x`,
        support_level: "historical_experimental",
        target_angular_exact: `${sourceMajor + 1}.0.0`,
        target_cli_exact: `${sourceMajor + 1}.0.0`,
        blockers: [],
        warnings: [],
      };
    }),
    selected_profile: null,
    blockers: [],
    warnings: [],
    package: {},
    package_checksum: "sha256:feasibility",
    artifact_ids: [],
    artifact_checksums: {},
    artifact_links: {},
    gate_id: "G05",
    gate_version: "g05-v1",
    gate_status: "approved",
    gate_decision: null,
    state_version: 1,
    event_sequence: 1,
    idempotent_replay: false,
  };
}

function plan(routeIds: string[]): PlanResponse {
  return {
    run_id: "run-fixture",
    status: "approved",
    plan: {
      plan_id: "plan-1",
      run_id: "run-fixture",
      version: 1,
      source_family: "angular-17.x",
      source_exact: "17.3.0",
      target_family: "angular-21.x",
      route: routeIds,
      mode: "staged",
      catalogue_version: "catalog-v1",
      stage_plan_strategy: "exact",
      approval_policy: "human",
      repair_policy: { policy_id: "repair-v1", enabled: true, proposer_reviewer_required: true, human_apply_required: true },
      command_policy: "registered",
      artifact_policy: "immutable",
      checksum: "sha256:plan",
    },
    stage_plan: {
      stage_plan_id: "stage-plan-1",
      stage_id: routeIds[0],
      plan_version: 1,
      input_fingerprint: "sha256:input",
      source_family: "angular-17.x",
      source_exact: "17.3.0",
      target_family: "angular-18.x",
      target_exact: "18.2.0",
      execution_profile_id: "profile-1",
      commands: {},
      build_system_decision: { decision_id: "d", builder: "b", action: "preserve", rationale: "r", checksum: "sha256:d" },
      validation_policy: { policy_id: "v", baseline_comparison_required: true, route_comparison_required: true, backend_comparison_required: true, required_checks: ["build"] },
      recovery_policy: { policy_id: "r", safe_boundaries: [], rerun_read_only_steps: true, reconstruct_mutating_steps: true },
      repair_policy: { policy_id: "p", enabled: true, proposer_reviewer_required: true, human_apply_required: true },
      forbidden_change_policy: { policy_id: "f", actions: [] },
      checksum: "sha256:stage",
    },
    plan_checksum: "sha256:plan",
    stage_plan_checksum: "sha256:stage",
    artifact_ids: [],
    artifact_checksums: {},
    artifact_links: {},
    builder_decision: {},
    state_version: 1,
    event_sequence: 1,
    idempotent_replay: false,
  };
}

describe("buildApprovedJourneyRoute", () => {
  it("orders the complete route by the approved plan and enriches it with feasibility metadata", () => {
    const route = buildApprovedJourneyRoute(
      plan(["stage-17-18", "stage-18-19", "stage-19-20", "stage-20-21"]),
      feasibility(["stage-17-18", "stage-18-19", "stage-19-20", "stage-20-21"]),
    );

    expect(route).toEqual([
      { stageId: "stage-17-18", sourceMajor: 17, targetMajor: 18 },
      { stageId: "stage-18-19", sourceMajor: 18, targetMajor: 19 },
      { stageId: "stage-19-20", sourceMajor: 19, targetMajor: 20 },
      { stageId: "stage-20-21", sourceMajor: 20, targetMajor: 21 },
    ]);
  });

  it("falls back to the approved feasibility route when no plan exists yet", () => {
    const route = buildApprovedJourneyRoute(
      null,
      feasibility(["stage-11-12", "stage-12-13", "stage-13-14"]),
    );

    expect(route).toHaveLength(3);
    expect(route[0]).toMatchObject({ stageId: "stage-11-12", sourceMajor: 17, targetMajor: 18 });
    expect(route.at(-1)).toMatchObject({ stageId: "stage-13-14", sourceMajor: 19, targetMajor: 20 });
  });

  it("yields no stages when neither plan nor feasibility exists", () => {
    expect(buildApprovedJourneyRoute(null, null)).toEqual([]);
  });
});

describe("useApprovedJourneyRoute", () => {
  it("fetches the approved route only while enabled and loads plan plus feasibility in parallel", async () => {
    vi.mocked(getPlan).mockResolvedValue(plan(["stage-17-18", "stage-18-19", "stage-19-20", "stage-20-21"]));
    vi.mocked(getFeasibility).mockResolvedValue(feasibility(["stage-17-18", "stage-18-19", "stage-19-20", "stage-20-21"]));

    const { result, rerender } = renderHook(
      ({ enabled }) => useApprovedJourneyRoute("run-fixture", enabled, 1),
      { initialProps: { enabled: false } },
    );
    expect(result.current.status).toBe("disabled");
    expect(getPlan).not.toHaveBeenCalled();

    rerender({ enabled: true });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(getPlan).toHaveBeenCalledOnce();
    expect(getFeasibility).toHaveBeenCalledOnce();
    expect(result.current.route).toHaveLength(4);
  });

  it("reports empty when both authoritative endpoints are absent", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("missing", 404));
    vi.mocked(getFeasibility).mockRejectedValue(new ApiClientError("missing", 404));

    const { result } = renderHook(() => useApprovedJourneyRoute("run-fixture", true, 1));
    await waitFor(() => expect(result.current.status).toBe("empty"));
    expect(result.current.route).toBeNull();
  });

  it("refetches the authoritative plan route when planning events advance after the feasibility-only load", async () => {
    const routeIds = [
      "angular-11-to-12--38e936ede40ca28c",
      "angular-12-to-13--d8117f08b24caed0",
      "angular-13-to-14--b9066112bb2c2cb8",
      "angular-14-to-15--e80e030bc9108e80",
      "angular-15-to-16--46af0d34c4b5f108",
      "angular-16-to-17--c4061946ab968291",
      "angular-17-to-18--86db4495eb1f9866",
      "angular-18-to-19--e417522667652d0a",
      "angular-19-to-20--d70ff163a0a918fb",
      "angular-20-to-21--9e3a0703f778e629",
    ];
    vi.mocked(getPlan).mockRejectedValueOnce(new ApiClientError("missing", 404));
    vi.mocked(getFeasibility).mockResolvedValue(feasibility(routeIds));

    const { result, rerender } = renderHook(
      ({ refreshKey }) => useApprovedJourneyRoute("run-fixture", true, refreshKey),
      { initialProps: { refreshKey: 1 } },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.route?.map((stage) => stage.stageId)).toEqual(routeIds);

    vi.mocked(getPlan).mockResolvedValue(plan(routeIds));
    const planCallsBefore = vi.mocked(getPlan).mock.calls.length;
    rerender({ refreshKey: 2 });
    await waitFor(() => expect(getPlan).toHaveBeenCalledTimes(planCallsBefore + 1));
    await waitFor(() => expect(result.current.route?.map((stage) => stage.stageId)).toEqual(routeIds));
  });

  it("reports failed when an authoritative endpoint errors beyond not-found", async () => {
    vi.mocked(getPlan).mockResolvedValue(plan(["stage-17-18"]));
    vi.mocked(getFeasibility).mockRejectedValue(new Error("network unavailable"));

    const { result } = renderHook(() => useApprovedJourneyRoute("run-fixture", true, 1));
    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.route).toBeNull();
  });

  it("preserves the confirmed route when a same-run refresh fails", async () => {
    vi.mocked(getPlan).mockResolvedValue(plan(["stage-17-18", "stage-18-19", "stage-19-20", "stage-20-21"]));
    vi.mocked(getFeasibility).mockResolvedValue(feasibility(["stage-17-18", "stage-18-19", "stage-19-20", "stage-20-21"]));

    const { result, rerender } = renderHook(
      ({ refreshKey }) => useApprovedJourneyRoute("run-fixture", true, refreshKey),
      { initialProps: { refreshKey: 1 } },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.route).toHaveLength(4);

    vi.mocked(getPlan).mockRejectedValue(new Error("network unavailable"));
    vi.mocked(getFeasibility).mockRejectedValue(new Error("network unavailable"));
    rerender({ refreshKey: 2 });
    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.route).toHaveLength(4);
  });

  it("invalidates the previous run's route as soon as runId changes", async () => {
    vi.mocked(getPlan).mockResolvedValue(plan(["stage-17-18", "stage-18-19", "stage-19-20", "stage-20-21"]));
    vi.mocked(getFeasibility).mockResolvedValue(feasibility(["stage-17-18", "stage-18-19", "stage-19-20", "stage-20-21"]));

    const { result, rerender } = renderHook(
      ({ runId }) => useApprovedJourneyRoute(runId, true, 1),
      { initialProps: { runId: "run-a" } },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.route).toHaveLength(4);

    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("missing", 404));
    vi.mocked(getFeasibility).mockRejectedValue(new ApiClientError("missing", 404));
    rerender({ runId: "run-b" });
    expect(result.current.route).toBeNull();

    await waitFor(() => expect(result.current.status).toBe("empty"));
    expect(result.current.route).toBeNull();
  });

  it("keeps the route null when the first-ever load fails", async () => {
    vi.mocked(getPlan).mockRejectedValue(new Error("network unavailable"));
    vi.mocked(getFeasibility).mockRejectedValue(new Error("network unavailable"));

    const { result } = renderHook(() => useApprovedJourneyRoute("run-fixture", true, 1));
    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.route).toBeNull();
  });
});