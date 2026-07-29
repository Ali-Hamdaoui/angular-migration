import { createApiClient } from "@/api/client";
import { getAssistantMessages, sendAssistantMessage, streamAssistantEvents } from "@/api/assistant";

describe("assistant API client", () => {
  it("uses the run-scoped typed POST and GET contract", async () => {
    const response = { message_id: "m1", message_order: 1, conversation_id: "c1", run_id: "run/1", answer: "state", current_phase: "Planning", current_stage: "unknown", workflow_status: "WAITING", current_gate: "G06", current_blocker: "unknown", next_permitted_action: "approval", workflow_state_version: 3, stale: false, evidence_references: [], proof_label: "authoritative persisted fact", usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 }, response_status: "completed", failure_reason: null };
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ run_id: "run/1", conversation_id: "c1", messages: [response] }), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 201 }));
    const client = createApiClient("http://backend.test", fetchMock);
    await expect(getAssistantMessages("run/1", "c1", client)).resolves.toMatchObject({ conversation_id: "c1" });
    await expect(sendAssistantMessage("run/1", { message: "Where is the migration now?", idempotency_key: "k" }, client)).resolves.toMatchObject({ answer: "state" });
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([["http://backend.test/api/v1/runs/run%2F1/assistant/messages?conversation_id=c1", "GET"], ["http://backend.test/api/v1/runs/run%2F1/assistant/messages", "POST"]]);
  });

  it("parses split and multiple SSE frames, ignores heartbeats, and sends the durable cursor", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      ": heartbeat\n\n",
      "id: 1\nevent: ASSISTANT_RESPONSE_STARTED\ndata: {\"sequence\":1,\"event_type\":\"ASSISTANT_RESPONSE_STARTED\",\n",
      "data: \"payload\":{\"safe\":true}}\n\n",
      "id: 2\nevent: ASSISTANT_CONTEXT_BUILT\ndata: {\"sequence\":2,\"event_type\":\"ASSISTANT_CONTEXT_BUILT\",\"payload\":{}}\n\n",
    ];
    const stream = new ReadableStream<Uint8Array>({
      start(controller) { chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk))); controller.close(); },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const events: unknown[] = [];
    const heartbeats: number[] = [];
    const pending = streamAssistantEvents("run/1", 7, controller.signal, (event) => events.push(event), () => heartbeats.push(1));
    await expect(pending).rejects.toThrow("disconnected");
    expect(events).toHaveLength(2);
    expect(heartbeats).toHaveLength(1);
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ "Last-Event-ID": "7", Accept: "text/event-stream" });
  });

  it("turns malformed event data into a reconnectable rejection", async () => {
    const stream = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode("event: ASSISTANT_RESPONSE_COMPLETED\ndata: {bad}\n\n")); controller.close(); } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));
    await expect(streamAssistantEvents("run-1", 0, new AbortController().signal, () => undefined, () => undefined)).rejects.toThrow();
  });
});
