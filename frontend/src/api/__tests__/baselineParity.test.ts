import { describe, expect, it, vi } from "vitest";
import { captureBaselineParity, getBaselineParitySection } from "@/api/baselineParity";
import type { createApiClient } from "@/api/client";

function client() {
  return { get: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}) } as unknown as ReturnType<typeof createApiClient>;
}

describe("baseline parity API", () => {
  it("encodes run IDs and uses documented evidence routes", async () => {
    const api = client();
    const request = { expected_state_version: 4, idempotency_key: "parity-1", actor: "operator" };
    await captureBaselineParity("run/1", request, api);
    await getBaselineParitySection("run/1", "backend-integration", api);
    expect(api.post).toHaveBeenCalledWith("/api/v1/runs/run%2F1/baseline/parity", request);
    expect(api.get).toHaveBeenCalledWith("/api/v1/runs/run%2F1/baseline/backend-integration");
  });
});
