import { describe, expect, it, vi } from "vitest";
import { decideG02, getG02Review } from "@/api/g02";
import { createApiClient } from "@/api/client";

const response = {
  run_id: "run-1", gate_id: "G02", gate_version: "g02-v1", status: "pending", decision: null,
  package: { run_id: "run-1", gate_id: "G02", gate_version: "g02-v1", state_version: 4, actor: "operator", policy_version: "source-snapshot-policy-v1", snapshot_id: "snapshot-1", source_fingerprint: "sha256:source", snapshot_fingerprint: "sha256:snapshot", artifact_set_checksum: "sha256:artifacts", artifacts: [], integrity: { before_fingerprint: "sha256:source", after_snapshot_fingerprint: "sha256:source", snapshot_fingerprint: "sha256:snapshot", manifest_checksum: "manifest-1", policy_version: "source-snapshot-policy-v1", source_read_only_verified: true, status: "verified" }, package_checksum: "sha256:package" },
  baseline_input_boundary: null, state_version: 4, event_sequence: 6, idempotent_replay: false, stale_reason: null, comment: null,
} as const;

describe("G02 API client", () => {
  it("gets the review package and posts a state-bound decision", async () => {
    const fetchImplementation = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchImplementation);

    await getG02Review("run/1", client);
    await decideG02("run/1", { expected_state_version: 4, idempotency_key: "g02-1", actor: "operator", decision: "approved", gate_id: "G02" }, client);

    expect(fetchImplementation).toHaveBeenNthCalledWith(1, "http://backend.test/api/v1/runs/run%2F1/approvals/G02", expect.objectContaining({ method: "GET" }));
    expect(fetchImplementation).toHaveBeenNthCalledWith(2, "http://backend.test/api/v1/runs/run%2F1/approvals/G02/decisions", expect.objectContaining({ method: "POST", body: expect.stringContaining("g02-1") }));
  });
});
