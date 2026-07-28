import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { decideG06, getPlanReview } from "@/api/planningReview";
import { usePlanReview } from "@/hooks/usePlanReview";
import type { PlanReviewResponse } from "@/types/planning";

vi.mock("@/api/planningReview", () => ({
  decideG06: vi.fn(),
  explainPlan: vi.fn(),
  getPlanReview: vi.fn(),
  revisePlan: vi.fn(),
}));

const checksum = `sha256:${"a".repeat(64)}`;
const pendingReview: PlanReviewResponse = {
  run_id: "run-1",
  status: "pending",
  plan: { version: 1, plan_id: "plan-1" },
  stage_plan: { stage_id: "stage-18-to-19", input_workspace_fingerprint: checksum },
  plan_checksum: checksum,
  stage_plan_checksum: checksum,
  diff: null,
  package: { narrative: { summary: "Review the generated plan." } },
  artifact_ids: ["artifact-1"],
  artifact_checksums: { "artifact-1": checksum },
  artifact_links: { "artifact-1": "/api/v1/artifacts/artifact-1" },
  gate_id: "G06",
  gate_version: "g06-v1",
  gate_status: "pending",
  gate_decision: null,
  package_checksum: checksum,
  artifact_set_checksum: checksum,
  computed_artifact_set_checksum: checksum,
  state_version: 7,
  event_sequence: 12,
  idempotent_replay: false,
};
const approvedReview: PlanReviewResponse = {
  ...pendingReview,
  status: "approved_for_execution",
  gate_status: "approved",
  gate_decision: "approve",
  state_version: 8,
  event_sequence: 13,
};
const waitingG06Job = { id: "job-1", status: "waiting_g06", current_step: "waiting_g06", attempt: 1, max_attempts: 3, correlation_id: "planning:run-1", updated_at: "2026-07-28T16:00:00Z" };

describe("usePlanReview", () => {
  beforeEach(() => vi.clearAllMocks());

  it("applies the compact G06 decision and then reloads the full authoritative review", async () => {
    vi.mocked(getPlanReview).mockResolvedValueOnce(pendingReview).mockResolvedValue(approvedReview);
    vi.mocked(decideG06).mockResolvedValue({
      run_id: "run-1",
      gate_id: "G06",
      gate_version: "g06-v1",
      decision: "approve",
      status: "approved",
      accepted: true,
      package_checksum: checksum,
      artifact_set_checksum: checksum,
      plan_checksum: checksum,
      stage_plan_checksum: checksum,
      state_version: 8,
      event_sequence: 13,
      idempotent_replay: false,
    });
    const refreshAuthoritativeState = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => usePlanReview({
      runId: "run-1",
      stateVersion: 7,
      workflowEvents: [],
      planningJob: waitingG06Job,
      connectionStatus: "connecting",
      refreshAuthoritativeState,
    }));

    await act(async () => {});
    await act(async () => { await result.current.decide("approve", null); });

    expect(decideG06).toHaveBeenCalledWith("run-1", expect.objectContaining({
      expected_state_version: 7,
      gate_version: "g06-v1",
      decision: "approve",
      workspace_fingerprint: checksum,
    }));
    expect(refreshAuthoritativeState).toHaveBeenCalled();
    expect(result.current.review?.gate_status).toBe("approved");
    expect(result.current.review?.plan).toEqual(pendingReview.plan);
    expect(result.current.review?.stage_plan).toEqual(pendingReview.stage_plan);
  });
  it("reports an inconsistency when G06 should exist but its review package is missing", async () => {
    vi.mocked(getPlanReview).mockRejectedValue(new ApiClientError("missing", 404));
    const { result } = renderHook(() => usePlanReview({
      runId: "run-1",
      stateVersion: 7,
      workflowEvents: [],
      planningJob: waitingG06Job,
      connectionStatus: "connecting",
      refreshAuthoritativeState: vi.fn().mockResolvedValue(undefined),
    }));

    await act(async () => {});

    expect(result.current.status).toBe("failure");
    expect(result.current.error).toContain("authoritative G06 review package is missing");
    expect(result.current.error).toContain("planning:run-1");
  });

});
