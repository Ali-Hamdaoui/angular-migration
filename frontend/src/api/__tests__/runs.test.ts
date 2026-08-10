import { createApiClient } from "@/api/client";
import { cancelAuthoritativeRun, createAuthoritativeRun, getAuthoritativeRunState, getAuthoritativeRunTiming, retryAuthoritativeSourceIntake, startAuthoritativeRun } from "@/api/runs";

const mutation = { run_id: "run-1", status: "CREATED", state_version: 2, event_sequence: 1, graph_thread_id: "thread-1", idempotent_replay: false, artifacts: [] } as const;
const state = { ...mutation, run_phase: "PREFLIGHT_SNAPSHOT", phase_status: "running", approval_status: "approved", repair_status: "not_required", preflight_id: "preflight-1", source_path: "C:/source", target_output_path: "C:/target", created_at: "2026-07-15T00:00:00Z", updated_at: "2026-07-15T00:00:00Z", workflow_events: [] };
const timing = { run_id: "run-1", status: "COMPLETED", as_of: "2026-07-15T00:12:00Z", started_at: "2026-07-15T00:00:00Z", finished_at: "2026-07-15T00:12:00Z", total_duration_seconds: 720, total_measurement_status: "complete", activity: { llm: { duration_seconds: null, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" }, commands: { duration_seconds: null, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" }, human_approval_wait: { duration_seconds: null, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" }, repair: { duration_seconds: null, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" }, validation: { duration_seconds: null, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" }, sealing: { duration_seconds: null, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" } }, phases: [], stages: [] };

describe("authoritative run API client", () => {
  it("uses the versioned create, start, retry, cancel, and state endpoints", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(mutation), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...mutation, status: "SOURCE_VALIDATION_RUNNING", state_version: 4 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...mutation, status: "SOURCE_VALIDATION_RUNNING", state_version: 5 }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...mutation, status: "CANCELLED", state_version: 6 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(state), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(timing), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await expect(createAuthoritativeRun({ preflight_id: "preflight-1", input_checksum: "sha256:input", artifact_set_checksum: "sha256:artifacts", idempotency_key: "create-1", actor: "operator", client_constraints: { preserve_ui: true }, pricing_snapshot: {} }, client)).resolves.toMatchObject({ run_id: "run-1" });
    await expect(startAuthoritativeRun("run-1", { expected_state_version: 2, idempotency_key: "start-1", actor: "operator" }, client)).resolves.toMatchObject({ status: "SOURCE_VALIDATION_RUNNING" });
    await expect(retryAuthoritativeSourceIntake("run-1", { expected_state_version: 4, idempotency_key: "retry-1", actor: "operator" }, client)).resolves.toMatchObject({ status: "SOURCE_VALIDATION_RUNNING" });
    await expect(cancelAuthoritativeRun("run-1", { expected_state_version: 5, idempotency_key: "cancel-1", actor: "operator" }, client)).resolves.toMatchObject({ status: "CANCELLED" });
    await expect(getAuthoritativeRunState("run-1", client)).resolves.toMatchObject({ preflight_id: "preflight-1" });
    await expect(getAuthoritativeRunTiming("run-1", client)).resolves.toMatchObject({ total_duration_seconds: 720 });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["http://backend.test/api/v1/runs", "http://backend.test/api/v1/runs/run-1/start", "http://backend.test/api/v1/runs/run-1/retry-source-intake", "http://backend.test/api/v1/runs/run-1/cancel", "http://backend.test/api/v1/runs/run-1/state", "http://backend.test/api/v1/runs/run-1/timing"]);
  });
});
