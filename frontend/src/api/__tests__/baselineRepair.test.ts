import { describe, expect, it, vi } from "vitest";
import { applyBaselineRepair } from "@/api/baselineRepair";
import type { createApiClient } from "@/api/client";

function client() {
  return { get: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}) } as unknown as ReturnType<typeof createApiClient>;
}

describe("baseline repair API", () => {
  it("posts the governed BASELINE-TEST-001 repair to the documented endpoint", async () => {
    const api = client();
    const request = {
      expected_state_version: 12,
      idempotency_key: "baseline-repair-run-1-123",
      actor: "control-tower",
      recipe_id: "BASELINE-TEST-001",
      g03_package_checksum: "sha256:abc",
    } as const;
    await applyBaselineRepair("run/1", request, api);
    expect(api.post).toHaveBeenCalledWith("/api/v1/runs/run%2F1/baseline/repairs", request);
  });
});
