import { createApiClient } from "@/api/client";
import { cancelStageBuild, getStageBuildMatrix, startStageBuild } from "@/api/stageBuild";

describe("stageBuild API", () => {
  const fetchMock = vi.fn();

  it("uses versioned build-matrix routes", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status: "passed" }), { status: 200 })));
    const client = createApiClient("http://backend.test", fetchMock);
    await getStageBuildMatrix("run-1", "stage-1", client);
    await startStageBuild("run-1", "stage-1", { expected_state_version: 1, idempotency_key: "k1", actor: "operator" }, client);
    await cancelStageBuild("run-1", "stage-1", client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/build-matrix",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/build-matrix",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/build-matrix/cancel",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toMatchObject({ expected_state_version: 1 });
  });
});
