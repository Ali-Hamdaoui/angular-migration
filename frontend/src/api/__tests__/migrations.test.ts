import { createApiClient } from "@/api/client";
import { getHealth, getMockMigrationState, getVersion, validatePreflight } from "@/api/migrations";
import { mockMigrationRun } from "@/data/mockMigrationRun";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("migration API client", () => {
  it("fetches health, version, and backend-owned mock state through one client", async () => {
    const preflight = {
      run_id: "mock-run-angular-18-to-21",
      status: "passed",
      input_checksum: "sha256:test",
      expires_at: "2099-01-01T00:00:00Z",
      source_path: "C:/fixture",
      target_output_path: "C:/output/app",
      findings: [],
      capabilities: [],
      artifact: null
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ name: "AI Frontend Migration Factory API", version: "0.1.0", environment: "development" }))
      .mockResolvedValueOnce(jsonResponse(mockMigrationRun))
      .mockResolvedValueOnce(jsonResponse(preflight));
    const client = createApiClient("http://backend.test", fetchMock);

    await expect(getHealth(client)).resolves.toEqual({ status: "ok" });
    await expect(getVersion(client)).resolves.toMatchObject({ version: "0.1.0" });
    await expect(getMockMigrationState(client)).resolves.toEqual(mockMigrationRun);
    await expect(validatePreflight({
      source_path: "C:/fixture",
      target_output_path: "C:/output/app",
      target_angular_family: "21.x",
      migration_mode: "strict-functional-parity",
      auto_approval_enabled: false
    }, client)).resolves.toEqual(preflight);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/health",
      "http://backend.test/version",
      "http://backend.test/migrations/mock-state",
      "http://backend.test/migrations/preflight"
    ]);
    expect(fetchMock.mock.calls[3][1]).toMatchObject({ method: "POST" });
  });
});