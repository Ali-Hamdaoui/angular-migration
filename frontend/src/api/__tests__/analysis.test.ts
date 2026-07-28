import { createApiClient } from "@/api/client";
import { decideG04, generateAnalysis, getAnalysis, retryAnalysis } from "@/api/analysis";
import { describe, expect, it, vi } from "vitest";

describe("analysis API client", () => {
  it("uses encoded create, retry, snapshot, and G04 decision endpoints", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);
    await getAnalysis("run/1", client);
    await generateAnalysis("run/1", { expected_state_version: 4, idempotency_key: "analysis-1" }, client);
    await retryAnalysis("run/1", { expected_state_version: 5, failed_analysis_id: "analysis-failed-1", idempotency_key: "analysis-retry-1", reason: "Provider configuration corrected" }, client);
    await decideG04("run/1", { expected_state_version: 7, idempotency_key: "g04-1", gate_version: "g04-v1", package_checksum: "sha256:" + "b".repeat(64), decision: "approve" }, client);

    expect(fetchMock.mock.calls.map((call) => (call[0] as string))).toEqual([
      "http://backend.test/api/v1/runs/run%2F1/analysis",
      "http://backend.test/api/v1/runs/run%2F1/analysis",
      "http://backend.test/api/v1/runs/run%2F1/analysis/retries",
      "http://backend.test/api/v1/runs/run%2F1/approvals/G04/decisions",
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
      expected_state_version: 5,
      failed_analysis_id: "analysis-failed-1",
      idempotency_key: "analysis-retry-1",
      reason: "Provider configuration corrected",
    });
  });
});
