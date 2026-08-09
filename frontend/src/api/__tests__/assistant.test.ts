import { createApiClient } from "@/api/client";
import { getAssistantMessages, sendAssistantMessage } from "@/api/assistant";

describe("assistant API client", () => {
  it("uses the run-scoped typed POST and GET contract", async () => {
    const response = { message_id: "m1", message_order: 1, conversation_id: "c1", run_id: "run/1", answer: "state", current_phase: "Planning", current_stage: "unknown", workflow_status: "WAITING", current_gate: "G06", current_blocker: "unknown", next_permitted_action: "approval", workflow_state_version: 3, stale: false, evidence_references: [], proof_label: "authoritative persisted fact", usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 }, response_status: "completed", failure_reason: null };
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ run_id: "run/1", conversation_id: "c1", messages: [response] }), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 201 }));
    const client = createApiClient("http://backend.test", fetchMock);
    await expect(getAssistantMessages("run/1", "c1", client)).resolves.toMatchObject({ conversation_id: "c1" });
    await expect(sendAssistantMessage("run/1", { message: "Where is the migration now?", idempotency_key: "k" }, client)).resolves.toMatchObject({ answer: "state" });
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([["http://backend.test/api/v1/runs/run%2F1/assistant/messages?conversation_id=c1", "GET"], ["http://backend.test/api/v1/runs/run%2F1/assistant/messages", "POST"]]);
  });
});
