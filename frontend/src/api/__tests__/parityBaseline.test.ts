import { describe, expect, it, vi } from "vitest";
import { captureParityBaseline, getParityBaseline } from "@/api/parityBaseline";
import type { createApiClient } from "@/api/client";

const request = { expected_state_version: 4, idempotency_key: "parity-1", prerequisite_artifact_ids: ["artifact-1"], prerequisite_artifact_checksums: { "artifact-1": "sha256:one" } };
function client() { return { get: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}) } as unknown as ReturnType<typeof createApiClient>; }

describe("parity baseline API", () => {
  it("uses encoded documented routes and preserves authoritative request fields", async () => {
    const api = client(); await captureParityBaseline("run/1", request, api); await getParityBaseline("run/1", api);
    expect(api.post).toHaveBeenCalledWith("/api/v1/runs/run%2F1/discovery/parity-baseline", request);
    expect(api.get).toHaveBeenCalledWith("/api/v1/runs/run%2F1/discovery/parity-baseline");
  });
});
