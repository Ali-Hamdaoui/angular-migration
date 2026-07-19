import { createApiClient } from "@/api/client";
import { createPlan, getPlan, getStagePlan } from "@/api/plans";
import { describe, expect, it, vi } from "vitest";

describe("plans API client", () => {
  it("uses encoded plan and stage endpoints", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);
    await getPlan("run/1", client);
    await getStagePlan("run/1", "stage/18-19", client);
    await createPlan("run/1", { expected_state_version: 2, idempotency_key: "plan-1", source_exact: "18.2.13", source_family: "angular-18.x", target_family: "angular-21.x", catalogue_version: "catalog-v1", input_fingerprint: "sha256:" + "a".repeat(64), execution_profile_id: "profile-1", stage_route: [["angular-18.x", "angular-19.x", "stage-18-to-19", "19.2.0"]], builder: "@angular-devkit/build-angular:application", prerequisite_artifacts: [{ artifact_id: "fact-1", checksum: "sha256:" + "b".repeat(64) }] }, client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run%2F1/plan",
      "http://backend.test/api/v1/runs/run%2F1/stages/stage%2F18-19/plan",
      "http://backend.test/api/v1/runs/run%2F1/plans",
    ]);
  });
});
