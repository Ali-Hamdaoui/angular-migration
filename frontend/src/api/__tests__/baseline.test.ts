import { createApiClient } from "@/api/client";
import { authorizeBaselineInstall, createBaselineWorkspace, getBaseline, getBaselineCommand, installBaseline, prequalifyBaseline } from "@/api/baseline";

describe("baseline API", () => {
  it("uses the versioned baseline preparation and installation routes", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status: "workspace_ready" }), { status: 200 })));
    const client = createApiClient("http://backend.test", fetchMock);
    const request = { expected_state_version: 4, idempotency_key: "baseline-1", actor: "operator" };
    await getBaseline("run/1", client);
    await createBaselineWorkspace("run/1", request, client);
    await prequalifyBaseline("run/1", request, client);
    await authorizeBaselineInstall("run/1", { ...request, decision: "authorize" }, client);
    await installBaseline("run/1", { ...request, runtime_profile_id: "profile-1", runtime_checksum: "sha256:runtime" }, client);
    await getBaselineCommand("run/1", "execution/1", client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run%2F1/baseline",
      "http://backend.test/api/v1/runs/run%2F1/baseline/workspace",
      "http://backend.test/api/v1/runs/run%2F1/baseline/prequalify",
      "http://backend.test/api/v1/runs/run%2F1/baseline/install-authorizations",
      "http://backend.test/api/v1/runs/run%2F1/baseline/install",
      "http://backend.test/api/v1/runs/run%2F1/commands/execution%2F1",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[4][1].body as string)).toMatchObject({ runtime_profile_id: "profile-1", runtime_checksum: "sha256:runtime" });
  });
});