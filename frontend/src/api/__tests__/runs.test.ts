import { createApiClient } from "@/api/client";
import { createAuthoritativeRun, getAuthoritativeRunState, startAuthoritativeRun } from "@/api/runs";

const mutation = { run_id: "run-1", status: "CREATED", state_version: 2, event_sequence: 1, graph_thread_id: "thread-1", idempotent_replay: false, artifacts: [] } as const;
const state = { ...mutation, run_phase: "PREFLIGHT_SNAPSHOT", phase_status: "running", approval_status: "approved", repair_status: "not_required", preflight_id: "preflight-1", source_path: "C:/source", target_output_path: "C:/target", created_at: "2026-07-15T00:00:00Z", updated_at: "2026-07-15T00:00:00Z", workflow_events: [] };

describe("authoritative run API client", () => {
  it("uses the versioned create, start, and state endpoints", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(mutation), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...mutation, status: "SOURCE_VALIDATION_RUNNING", state_version: 4 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(state), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await expect(createAuthoritativeRun({ preflight_id: "preflight-1", input_checksum: "sha256:input", artifact_set_checksum: "sha256:artifacts", idempotency_key: "create-1", actor: "operator", client_constraints: { preserve_ui: true }, pricing_snapshot: {} }, client)).resolves.toMatchObject({ run_id: "run-1" });
    await expect(startAuthoritativeRun("run-1", { expected_state_version: 2, idempotency_key: "start-1", actor: "operator" }, client)).resolves.toMatchObject({ status: "SOURCE_VALIDATION_RUNNING" });
    await expect(getAuthoritativeRunState("run-1", client)).resolves.toMatchObject({ preflight_id: "preflight-1" });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["http://backend.test/api/v1/runs", "http://backend.test/api/v1/runs/run-1/start", "http://backend.test/api/v1/runs/run-1/state"]);
  });
});
