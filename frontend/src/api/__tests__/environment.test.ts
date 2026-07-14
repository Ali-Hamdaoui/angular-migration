import { createApiClient } from "@/api/client";
import { getEnvironmentDiagnostics, refreshEnvironment } from "@/api/migrations";

const snapshot = {
  snapshot_id: "environment-test",
  captured_at: "2026-07-14T00:00:00Z",
  policy_version: "environment-readiness-v1",
  status: "available",
  runtimes: [],
  node_npm_npx_paired: true,
  git_ready: true,
  python_ready: true,
  storage: { database_path: "C:/state.db", artifact_root: "C:/runs", writable: true, local_filesystem: true, free_bytes: 1, status: "available" },
  network: { registry_configured: true, proxy_configured: false, https_proxy_configured: false, strict_ssl: true, custom_ca_configured: false, credentials_redacted: true },
  blockers: [],
  warnings: [],
  checksum: "sha256:test",
};

describe("environment diagnostics API", () => {
  it("reads and refreshes typed environment diagnostics", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot, artifact: null }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshot, artifact: null }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await expect(getEnvironmentDiagnostics(client)).resolves.toMatchObject({ snapshot: { checksum: "sha256:test" } });
    await expect(refreshEnvironment({ idempotency_key: "refresh-1", actor: "operator" }, client)).resolves.toMatchObject({ snapshot: { status: "available" } });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/environment/diagnostics",
      "http://backend.test/environment/refresh",
    ]);
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  });
});