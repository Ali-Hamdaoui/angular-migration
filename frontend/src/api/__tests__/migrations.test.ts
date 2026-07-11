import { createApiClient } from "@/api/client";
import { createMockMigration, getHealth, getMockMigrationState, getVersion, validatePreflight } from "@/api/migrations";
import { mockMigrationRun } from "@/data/mockMigrationRun";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("migration API client", () => {
  it("fetches health, version, preflight, create-run, and backend-owned mock state through one client", async () => {
    const preflight = { checksum: "sha256:test", status: "passed" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ name: "AI Frontend Migration Factory API", version: "0.1.0", environment: "development" }))
      .mockResolvedValueOnce(jsonResponse(preflight))
      .mockResolvedValueOnce(jsonResponse(mockMigrationRun))
      .mockResolvedValueOnce(jsonResponse(mockMigrationRun));
    const client = createApiClient("http://backend.test", fetchMock);

    await expect(getHealth(client)).resolves.toEqual({ status: "ok" });
    await expect(getVersion(client)).resolves.toMatchObject({ version: "0.1.0" });
    await expect(validatePreflight({
      source_path: "source",
      target_output_path: "target",
      target_angular_family: "21.x",
      migration_mode: "strict-functional-parity",
      auto_approval_enabled: false
    }, client)).resolves.toEqual(preflight);
    await expect(createMockMigration({ preflight_checksum: "sha256:test" }, client)).resolves.toEqual(mockMigrationRun);
    await expect(getMockMigrationState(client)).resolves.toEqual(mockMigrationRun);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/health",
      "http://backend.test/version",
      "http://backend.test/migrations/preflight",
      "http://backend.test/migrations/mock",
      "http://backend.test/migrations/mock-state"
    ]);
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: "POST" });
    expect(fetchMock.mock.calls[3][1]).toMatchObject({ method: "POST" });
  });
});
