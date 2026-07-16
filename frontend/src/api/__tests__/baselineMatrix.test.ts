import { describe, expect, it, vi } from "vitest";
import { getBaselineTargets, getBaselineValidation, startBaselineValidation } from "@/api/baselineMatrix";
import type { createApiClient } from "@/api/client";

function client() {
  return { get: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}) } as unknown as ReturnType<typeof createApiClient>;
}

describe("baseline matrix API", () => {
  it("encodes run IDs when reading the target inventory", async () => {
    const api = client();
    await getBaselineTargets("run/with spaces", api);
    expect(api.get).toHaveBeenCalledWith("/api/v1/runs/run%2Fwith%20spaces/baseline/targets");
  });

  it("uses the documented operation endpoints", async () => {
    const api = client();
    const request = { expected_state_version: 4, idempotency_key: "matrix-1", actor: "operator" };
    await startBaselineValidation("run-1", "build", request, api);
    await startBaselineValidation("run-1", "test", request, api);
    await startBaselineValidation("run-1", "lint", request, api);
    expect(api.post).toHaveBeenNthCalledWith(1, "/api/v1/runs/run-1/baseline/builds", request);
    expect(api.post).toHaveBeenNthCalledWith(2, "/api/v1/runs/run-1/baseline/tests", request);
    expect(api.post).toHaveBeenNthCalledWith(3, "/api/v1/runs/run-1/baseline/lint", request);
  });

  it("reads a kind-specific authoritative result", async () => {
    const api = client();
    await getBaselineValidation("run-1", "lint", api);
    expect(api.get).toHaveBeenCalledWith("/api/v1/runs/run-1/baseline/lint");
  });
});
