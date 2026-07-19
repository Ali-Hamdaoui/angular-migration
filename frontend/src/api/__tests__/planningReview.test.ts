import { createApiClient } from "@/api/client";
import { decideG06, explainPlan, getPlanReview, revisePlan } from "@/api/planningReview";
import { describe, expect, it, vi } from "vitest";

describe("planning review API client", () => {
  it("uses encoded run-scoped review endpoints", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);
    const checksum = "sha256:" + "a".repeat(64);
    await getPlanReview("run/1", client);
    await revisePlan("run/1", { expected_state_version: 2, idempotency_key: "revision-1", plan: {}, stage_plan: {}, changes: { builder: "builder" }, artifact_set_checksum: checksum, prerequisite_artifacts: [] }, client);
    await explainPlan("run/1", { expected_state_version: 2, idempotency_key: "explain-1", plan: {}, stage_plan: {}, plan_version: 1, artifact_set_checksum: checksum, prerequisite_artifacts: [] }, client);
    await decideG06("run/1", { expected_state_version: 2, idempotency_key: "g06-1", gate_version: "g06-v1", artifact_set_checksum: checksum, plan_checksum: checksum, stage_plan_checksum: checksum, decision: "approve" }, client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run%2F1/plan/review",
      "http://backend.test/api/v1/runs/run%2F1/plan/revisions",
      "http://backend.test/api/v1/runs/run%2F1/plan/explanation",
      "http://backend.test/api/v1/runs/run%2F1/approvals/G06/decisions",
    ]);
  });
});
