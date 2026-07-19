import { createApiClient } from "@/api/client";
import { getStageSeal, startCopyForward, submitG12Decision, submitStageSealRequest } from "@/api/stageSeal";

describe("stageSeal API", () => {
  const fetchMock = vi.fn();

  it("uses versioned seal, G12, and copy-forward routes", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status: "sealed" }), { status: 200 })));
    const client = createApiClient("http://backend.test", fetchMock);
    await getStageSeal("run-1", "stage-1", client);
    await submitStageSealRequest("run-1", "stage-1", { expected_state_version: 1, idempotency_key: "k1", actor: "operator" }, client);
    await submitG12Decision("run-1", "stage-1", { expected_state_version: 2, idempotency_key: "k2", actor: "operator", g12_decision: "APPROVED" }, client);
    await startCopyForward("run-1", "stage-1", client);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/seal",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/seal",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/seal/g12",
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/seal/copy-forward",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[2][1].body as string)).toMatchObject({ g12_decision: "APPROVED" });
  });
});
