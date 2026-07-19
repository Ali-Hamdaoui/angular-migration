import { createApiClient } from "@/api/client";
import { decideG04, generateAnalysis, getAnalysis } from "@/api/analysis";
import { describe, expect, it, vi } from "vitest";

describe("analysis API client", () => {
  it("uses encoded snapshot, generation, and G04 decision endpoints", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);
    await getAnalysis("run/1", client);
    await generateAnalysis("run/1", { expected_state_version: 4, idempotency_key: "analysis-1", prerequisite_artifacts: [{ artifact_id: "fact-1", checksum: "sha256:" + "a".repeat(64) }] }, client);
    await decideG04("run/1", { expected_state_version: 7, idempotency_key: "g04-1", gate_version: "g04-v1", package_artifact_set_checksum: "sha256:" + "b".repeat(64), decision: "approve" }, client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run%2F1/analysis",
      "http://backend.test/api/v1/runs/run%2F1/analysis",
      "http://backend.test/api/v1/runs/run%2F1/approvals/G04/decisions",
    ]);
  });
});
