import { createApiClient } from "@/api/client";
import { executeApprovedCommand, getCommandExecution, listCommandExecutions } from "@/api/commands";

function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }); }

describe("command execution API client", () => {
  it("submits only the accepted authorization contract and supports run-scoped rehydration", async () => {
    const execution = { execution_id: "exec-1", run_id: "run-1", command_id: "npm-ci", status: "queued", state_version: 8, event_sequence: 4, idempotent_replay: false, artifact_ids: [] };
    const fetchMock = vi.fn().mockResolvedValueOnce(response(execution)).mockResolvedValueOnce(response({ run_id: "run-1", executions: [execution], total: 1 })).mockResolvedValueOnce(response(execution));
    const client = createApiClient("http://backend.test", fetchMock);

    await executeApprovedCommand("run-1", { authorization_decision_id: "auth-1", expected_state_version: 7, idempotency_key: "attempt-1", requested_by: "control-tower" }, client);
    await listCommandExecutions("run-1", client);
    await getCommandExecution("run-1", "exec-1", client);

    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ authorization_decision_id: "auth-1", expected_state_version: 7, idempotency_key: "attempt-1", requested_by: "control-tower" });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["http://backend.test/api/v1/runs/run-1/commands", "http://backend.test/api/v1/runs/run-1/commands", "http://backend.test/api/v1/runs/run-1/commands/exec-1"]);
  });
});
