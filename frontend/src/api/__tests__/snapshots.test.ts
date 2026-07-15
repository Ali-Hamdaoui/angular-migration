import { createApiClient } from "@/api/client";
import { createSourceSnapshot, getSourceSnapshot } from "@/api/snapshots";

const snapshot = {
  snapshot_id: "snapshot-1",
  run_id: "run-1",
  status: "created",
  source_path: "C:/source",
  snapshot_path: "D:/output/.migration-factory/runs/run-1/source-snapshot/snapshot-1",
  manifest_id: "manifest-1",
  fingerprint: "sha256:fingerprint",
  policy_version: "source-snapshot-policy-v1",
  file_count: 2,
  total_size_bytes: 42,
  exclusions: [],
  git_metadata: {},
  artifacts: [],
  state_version: 3,
  event_sequence: 2,
  idempotent_replay: false,
  error_code: null,
  error_message: null,
  created_at: "2026-07-15T00:00:00Z",
} as const;

describe("source snapshot API client", () => {
  it("uses the versioned create and inspect endpoints", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(snapshot), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(snapshot), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await expect(createSourceSnapshot("run-1", {
      expected_state_version: 2,
      idempotency_key: "snapshot-request",
      actor: "operator",
    }, client)).resolves.toMatchObject({ snapshot_id: "snapshot-1" });
    await expect(getSourceSnapshot("run-1", "snapshot-1", client)).resolves.toMatchObject({ fingerprint: "sha256:fingerprint" });
    expect(fetchMock.mock.calls.map(([url, options]) => [url, options?.method])).toEqual([
      ["http://backend.test/api/v1/runs/run-1/snapshots", "POST"],
      ["http://backend.test/api/v1/runs/run-1/snapshots/snapshot-1", "GET"],
    ]);
  });
});
