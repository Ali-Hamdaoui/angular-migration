import { createApiClient } from "@/api/client";
import { getLlmActivity, getLlmReadiness, getLlmUsage, invokeLlmSmoke } from "@/api/llm";

describe("LLM diagnostics API client", () => {
  it("uses the governed readiness, smoke, activity, and usage endpoints", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ status: "ready", run_id: "run-1", invocations: [], invocation_count: 0, llm_calls: 0, retry_calls: 0, usage_recorded_calls: 0, usage_unavailable_calls: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, input_cost_usd: 0, output_cost_usd: 0, total_cost_usd: 0, pricing_versions: [], by_phase: [], by_stage: [], by_role: [], by_purpose: [], records: [] }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);
    await getLlmReadiness(client);
    await invokeLlmSmoke({ run_id: "run-1", expected_state_version: 2, idempotency_key: "smoke-1" }, client);
    await getLlmActivity("run-1", client);
    await getLlmUsage("run-1", client);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
