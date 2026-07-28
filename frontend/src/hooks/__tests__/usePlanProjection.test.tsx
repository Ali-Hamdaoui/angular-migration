import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { getPlan } from "@/api/plans";
import { usePlanProjection } from "@/hooks/usePlanProjection";

vi.mock("@/api/plans", () => ({ getPlan: vi.fn() }));

const base = { runId: "run-1", stateVersion: 7, workflowEvents: [] as Array<{ event_type: string; sequence: number }>, connectionStatus: "open" };
const generatingJob = { id: "job-1", status: "generating_plan", current_step: "generating_plan", attempt: 1, max_attempts: 3, updated_at: "2026-07-28T16:00:00Z" };
const waitingG06Job = { id: "job-1", status: "waiting_g06", current_step: "waiting_g06", attempt: 1, max_attempts: 3, correlation_id: "planning:run-1", updated_at: "2026-07-28T16:00:00Z" };

describe("usePlanProjection", () => {
  beforeEach(() => vi.clearAllMocks());

  it("treats plan 404 as expected while the backend is generating the plan", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("missing", 404));
    const { result } = renderHook(() => usePlanProjection({ ...base, planningJob: generatingJob }));
    await act(async () => {});
    expect(result.current.status).toBe("generating_plan");
    expect(result.current.error).toBeNull();
  });

  it("reports an authoritative inconsistency when the plan is missing after G06 became available", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("missing", 404));
    const { result } = renderHook(() => usePlanProjection({ ...base, planningJob: waitingG06Job }));
    await act(async () => {});
    expect(result.current.status).toBe("failure");
    expect(result.current.error).toContain("waiting_g06");
    expect(result.current.error).toContain("planning:run-1");
  });
});
