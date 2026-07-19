import { createApiClient } from "@/api/client";
import { cancelStageTests, getStageTestLogs, getStageTests, startStageTests } from "@/api/stageTests";

describe("stageTests API", () => {
  const fetchMock = vi.fn();

  it("uses versioned test routes", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status: "passed" }), { status: 200 })));
    const client = createApiClient("http://backend.test", fetchMock);
    await getStageTests("run-1", "stage-1", client);
    await startStageTests("run-1", "stage-1", { expected_state_version: 1, idempotency_key: "k1", actor: "operator" }, client);
    await cancelStageTests("run-1", "stage-1", client);
    await getStageTestLogs("run-1", "stage-1", "test-1", client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/tests",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/tests",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/tests/cancel",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/tests/test-1/logs",
    ]);
  });
});
