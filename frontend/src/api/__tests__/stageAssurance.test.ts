import { createApiClient } from "@/api/client";
import { getStageAssurance, submitG09Decision, updateStageAssurance } from "@/api/stageAssurance";

describe("stageAssurance API", () => {
  const fetchMock = vi.fn();

  it("uses versioned assurance and G09 routes", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status: "passed" }), { status: 200 })));
    const client = createApiClient("http://backend.test", fetchMock);
    await getStageAssurance("run-1", "stage-1", client);
    await updateStageAssurance("run-1", "stage-1", { expected_state_version: 1, idempotency_key: "k1", actor: "operator" }, client);
    await submitG09Decision("run-1", "stage-1", { expected_state_version: 2, idempotency_key: "k2", actor: "operator", decision: "ACCEPT_ALL", rationale: "All good" }, client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/assurance",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/assurance",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/assurance/g09",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[2][1].body as string)).toMatchObject({ decision: "ACCEPT_ALL" });
  });
});
