import { act, renderHook, waitFor } from "@testing-library/react";
import { ApiClientError } from "@/api/client";
import { listCommandExecutions } from "@/api/commands";
import { getTransformation } from "@/api/transformation";
import { useTransformation } from "@/hooks/useTransformation";
import type { TransformationProjection } from "@/types/transformation";

vi.mock("@/api/commands", () => ({ listCommandExecutions: vi.fn() }));
vi.mock("@/api/transformation", () => ({ getTransformation: vi.fn() }));

function makeTransformation(runId: string): TransformationProjection {
  return {
    run_id: runId,
    continuation_id: `continuation-${runId}`,
    stage_id: "stage-18-19",
    status: "running",
    current_node: "stage_transformation",
    state_version: 9,
    stage_status: "RUNNING",
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
  };
}

function commandList(runId: string) {
  return { run_id: runId, executions: [], total: 0 };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

describe("useTransformation", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("performs no requests while disabled and disabled refresh resolves without state churn", async () => {
    const { result } = renderHook(() => useTransformation("run-disabled", { enabled: false }));

    await waitFor(() => expect(result.current.status).toBe("disabled"));
    const beforeRefresh = result.current;
    await act(() => result.current.refresh());

    expect(getTransformation).not.toHaveBeenCalled();
    expect(listCommandExecutions).not.toHaveBeenCalled();
    expect(result.current).toEqual(beforeRefresh);
    expect(result.current.executionStatus).toBe("idle");
  });

  it("starts one projection request and one execution request when enabled", async () => {
    vi.mocked(getTransformation).mockResolvedValue(makeTransformation("run-enabled"));
    vi.mocked(listCommandExecutions).mockResolvedValue(commandList("run-enabled"));

    const { result } = renderHook(() => useTransformation("run-enabled", { enabled: true }));

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(getTransformation).toHaveBeenCalledTimes(1);
    expect(getTransformation).toHaveBeenCalledWith("run-enabled");
    expect(listCommandExecutions).toHaveBeenCalledTimes(1);
    expect(listCommandExecutions).toHaveBeenCalledWith("run-enabled");
    expect(result.current.executionStatus).toBe("ready");
  });

  it("reloads exactly once when the refresh key changes", async () => {
    vi.mocked(getTransformation).mockResolvedValue(makeTransformation("run-refresh"));
    vi.mocked(listCommandExecutions).mockResolvedValue(commandList("run-refresh"));
    const { rerender, result } = renderHook(
      ({ refreshKey }) => useTransformation("run-refresh", { enabled: true, refreshKey }),
      { initialProps: { refreshKey: 0 } },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));

    rerender({ refreshKey: 1 });

    await waitFor(() => expect(getTransformation).toHaveBeenCalledTimes(2));
    expect(listCommandExecutions).toHaveBeenCalledTimes(2);
  });

  it("retains the last confirmed projection when a same-run background refresh fails", async () => {
    const projection = makeTransformation("run-background");
    vi.mocked(getTransformation).mockResolvedValueOnce(projection);
    vi.mocked(listCommandExecutions).mockResolvedValue(commandList("run-background"));
    const { result } = renderHook(() => useTransformation("run-background", { enabled: true }));
    await waitFor(() => expect(result.current.projection).toBe(projection));
    vi.mocked(getTransformation).mockRejectedValueOnce(new ApiClientError("offline", 503));

    await act(() => result.current.refresh());

    expect(result.current.projection).toBe(projection);
    expect(result.current.status).toBe("ready");
    expect(result.current.refreshError).toBe("Background refresh failed; showing the last authoritative state.");
  });

  it("resets confirmed data for a new run and ignores the prior run's late response", async () => {
    const runA = deferred<TransformationProjection>();
    vi.mocked(getTransformation)
      .mockReturnValueOnce(runA.promise)
      .mockResolvedValueOnce(makeTransformation("run-b"));
    vi.mocked(listCommandExecutions).mockImplementation(async (runId) => commandList(runId));
    const { rerender, result } = renderHook(
      ({ runId }) => useTransformation(runId, { enabled: true }),
      { initialProps: { runId: "run-a" } },
    );

    rerender({ runId: "run-b" });
    expect(result.current.projection).toBeNull();
    await waitFor(() => expect(result.current.projection?.run_id).toBe("run-b"));
    await act(async () => runA.resolve(makeTransformation("run-a")));

    expect(result.current.projection?.run_id).toBe("run-b");
  });

  it("ignores an enabled request that completes after loading is disabled", async () => {
    const pending = deferred<TransformationProjection>();
    vi.mocked(getTransformation).mockReturnValue(pending.promise);
    vi.mocked(listCommandExecutions).mockResolvedValue(commandList("run-toggle"));
    const { rerender, result } = renderHook(
      ({ enabled }) => useTransformation("run-toggle", { enabled }),
      { initialProps: { enabled: true } },
    );

    rerender({ enabled: false });
    await waitFor(() => expect(result.current.status).toBe("disabled"));
    await act(async () => pending.resolve(makeTransformation("run-toggle")));

    expect(result.current.status).toBe("disabled");
    expect(result.current.projection).toBeNull();
  });

  it("restores confirmed ready status immediately when the same run is re-enabled with a stalled refresh", async () => {
    const confirmed = makeTransformation("run-re-enabled");
    const stalledProjection = deferred<TransformationProjection>();
    vi.mocked(getTransformation)
      .mockResolvedValueOnce(confirmed)
      .mockReturnValueOnce(stalledProjection.promise);
    vi.mocked(listCommandExecutions).mockImplementation(async () => commandList("run-re-enabled"));
    const { rerender, result } = renderHook(
      ({ enabled }) => useTransformation("run-re-enabled", { enabled }),
      { initialProps: { enabled: true } },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));

    rerender({ enabled: false });
    await waitFor(() => expect(result.current.status).toBe("disabled"));
    rerender({ enabled: true });

    expect(result.current.projection).toBe(confirmed);
    expect(result.current.status).toBe("ready");
    expect(result.current.executionStatus).toBe("loading");
  });
});
