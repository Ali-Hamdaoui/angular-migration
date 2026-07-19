import { createApiClient } from "@/api/client";
import { cancelStageValidation, getStageValidation, getStageValidationLogs, startStageValidation } from "@/api/stageValidation";

describe("stageValidation API", () => {
  const fetchMock = vi.fn();

  it("uses versioned install-static validation routes", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status: "passed" }), { status: 200 })));
    const client = createApiClient("http://backend.test", fetchMock);
    await getStageValidation("run-1", "stage-1", client);
    await startStageValidation("run-1", "stage-1", { expected_state_version: 1, idempotency_key: "k1", actor: "operator" }, client);
    await cancelStageValidation("run-1", "stage-1", client);
    await getStageValidationLogs("run-1", "stage-1", "val-1", client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/validation/install-static",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/validation/install-static",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/validation/install-static/cancel",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/validation/install-static/val-1/logs",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toMatchObject({ expected_state_version: 1, idempotency_key: "k1" });
  });
});
