import { createApiClient } from "@/api/client";
import { createBaselineWorkspace, getBaseline, prequalifyBaseline, authorizeBaselineInstall } from "@/api/baseline";

describe("baseline API", () => {
  it("uses the versioned baseline routes and typed request bodies", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status: "workspace_ready" }), { status: 200 })));
    const client = createApiClient("http://backend.test", fetchMock);
    const request = { expected_state_version: 4, idempotency_key: "baseline-1", actor: "operator" };
    await getBaseline("run/1", client);
    await createBaselineWorkspace("run/1", request, client);
    await prequalifyBaseline("run/1", request, client);
    await authorizeBaselineInstall("run/1", { ...request, decision: "authorize" }, client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run%2F1/baseline",
      "http://backend.test/api/v1/runs/run%2F1/baseline/workspace",
      "http://backend.test/api/v1/runs/run%2F1/baseline/prequalify",
      "http://backend.test/api/v1/runs/run%2F1/baseline/install-authorizations",
    ]);
  });
});
