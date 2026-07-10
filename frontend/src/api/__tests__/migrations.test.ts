import { createApiClient } from "@/api/client";
import { getHealth, getMockMigrationState, getVersion } from "@/api/migrations";
import { mockMigrationRun } from "@/data/mockMigrationRun";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("migration API client", () => {
  it("fetches health, version, and backend-owned mock state through one client", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ name: "AI Frontend Migration Factory API", version: "0.1.0", environment: "development" }))
      .mockResolvedValueOnce(jsonResponse(mockMigrationRun));
    const client = createApiClient("http://backend.test", fetchMock);

    await expect(getHealth(client)).resolves.toEqual({ status: "ok" });
    await expect(getVersion(client)).resolves.toMatchObject({ version: "0.1.0" });
    await expect(getMockMigrationState(client)).resolves.toEqual(mockMigrationRun);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/health",
      "http://backend.test/version",
      "http://backend.test/migrations/mock-state"
    ]);
  });
});