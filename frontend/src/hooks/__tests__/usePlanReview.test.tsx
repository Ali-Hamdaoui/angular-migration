import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { decideG06, getPlanReview } from "@/api/planningReview";
import { usePlanReview } from "@/hooks/usePlanReview";

vi.mock("@/api/planningReview", () => ({
  decideG06: vi.fn(),
  explainPlan: vi.fn(),
  getPlanReview: vi.fn(),
  revisePlan: vi.fn(),
}));

const checksum = "sha256:" + "a".repeat(64);
const review = {
  run_id: "run-1", status: "pending", plan: { version: 1 }, stage_plan: { stage_id: "stage-1" },
  plan_checksum: checksum, stage_plan_checksum: checksum, diff: null,
  package: { artifact_set_checksum: checksum }, artifact_ids: [], artifact_checksums: {}, artifact_links: {},
  gate_id: "G06", gate_version: "g06-v1", gate_status: "pending", gate_decision: null,
  package_checksum: checksum, state_version: 4, event_sequence: 8, idempotent_replay: false,
};

function renderPlanReview(refreshAuthoritativeState = vi.fn().mockResolvedValue(undefined)) {
  return {
    refreshAuthoritativeState,
    ...renderHook(() => usePlanReview({
      runId: "run-1",
      stateVersion: 4,
      workflowEvents: [],
      connectionStatus: "idle",
      refreshAuthoritativeState,
    })),
  };
}

describe("usePlanReview G06 mutation", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getPlanReview).mockResolvedValue(review);
  });

  it("refreshes authoritative run and review state after accepted G06", async () => {
    vi.mocked(decideG06).mockResolvedValue({
      run_id: "run-1", gate_id: "G06", gate_version: "g06-v1", decision: "approve",
      status: "approved", accepted: true, package_checksum: checksum, artifact_set_checksum: checksum,
      plan_checksum: checksum, stage_plan_checksum: checksum, state_version: 5, event_sequence: 9,
      idempotent_replay: false,
    });
    const { result, refreshAuthoritativeState } = renderPlanReview();
    await waitFor(() => expect(result.current.status).toBe("success"));
    vi.mocked(getPlanReview).mockClear();

    await act(() => result.current.decide("approve", null));

    expect(refreshAuthoritativeState).toHaveBeenCalledOnce();
    expect(getPlanReview).toHaveBeenCalledOnce();
    expect(result.current.review).toEqual(review);
  });

  it("reports G06 approval failure without refreshing authoritative state", async () => {
    vi.mocked(decideG06).mockRejectedValue(new Error("offline"));
    const { result, refreshAuthoritativeState } = renderPlanReview();
    await waitFor(() => expect(result.current.status).toBe("success"));

    await act(() => result.current.decide("approve", null));

    expect(result.current.status).toBe("failure");
    expect(result.current.error).toContain("G06 decision failed");
    expect(refreshAuthoritativeState).not.toHaveBeenCalled();
  });

  it("prevents duplicate G06 submissions", async () => {
    let resolveDecision!: (value: Awaited<ReturnType<typeof decideG06>>) => void;
    vi.mocked(decideG06).mockReturnValue(new Promise((resolve) => { resolveDecision = resolve; }));
    const { result } = renderPlanReview();
    await waitFor(() => expect(result.current.status).toBe("success"));

    let first!: ReturnType<typeof result.current.decide>;
    await act(async () => {
      first = result.current.decide("approve", null);
      void result.current.decide("approve", null);
    });
    expect(decideG06).toHaveBeenCalledOnce();

    resolveDecision({
      run_id: "run-1", gate_id: "G06", gate_version: "g06-v1", decision: "approve",
      status: "approved", accepted: true, package_checksum: checksum, artifact_set_checksum: checksum,
      plan_checksum: checksum, stage_plan_checksum: checksum, state_version: 5, event_sequence: 9,
      idempotent_replay: false,
    });
    await act(() => first);
  });
});
