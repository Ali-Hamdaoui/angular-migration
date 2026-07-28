import { createApiClient } from "@/api/client";
import { getPlan, getStagePlan } from "@/api/plans";
import { describe, expect, it, vi } from "vitest";

describe("plans API client", () => {
  it("exposes projection-only plan and stage endpoints for the operator UI", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);
    await getPlan("run/1", client);
    await getStagePlan("run/1", "stage/18-19", client);
    expect(fetchMock.mock.calls.map((call) => (call[0] as string))).toEqual([
      "http://backend.test/api/v1/runs/run%2F1/plan",
      "http://backend.test/api/v1/runs/run%2F1/stages/stage%2F18-19/plan",
    ]);
  });
});
