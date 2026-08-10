import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach } from "vitest";
import { ApiClientError } from "@/api/client";
import { LlmDiagnosticsPanel } from "@/components/LlmDiagnosticsPanel";
import { getLlmActivity, getLlmReadiness, getLlmUsage, invokeLlmSmoke } from "@/api/llm";
import type { LlmUsageResponse } from "@/types/llm";

vi.mock("@/api/llm", () => ({ getLlmActivity: vi.fn(), getLlmReadiness: vi.fn(), getLlmUsage: vi.fn(), invokeLlmSmoke: vi.fn() }));

const invocation = { invocation_id: "llm-1", run_id: "run-1", status: "completed" as const, role: "phase_proposer", task_type: "smoke_check", provider: "azure_openai", deployment_alias: "azure-openai", artifact_ids: ["artifact-usage"], artifact_checksums: { "artifact-usage": "sha256:usage" }, input_tokens: 10, output_tokens: 5, total_tokens: 15, input_cost_usd: 0.00001, output_cost_usd: 0.00002, total_cost_usd: 0.00003, retries: 1, latency_ms: 250, failure_code: null, state_version: 3, event_sequence: 4, idempotent_replay: false };

function usageResponse(runId: string, totalTokens: number): LlmUsageResponse {
  return { run_id: runId, invocation_count: 1, llm_calls: 1, retry_calls: 0, usage_recorded_calls: 1, usage_unavailable_calls: 0, input_tokens: totalTokens, output_tokens: 0, total_tokens: totalTokens, input_cost_usd: 0, output_cost_usd: 0, total_cost_usd: 0, pricing_versions: ["pricing-v1"], by_phase: [], by_stage: [], by_role: [], by_purpose: [], records: [] };
}

describe("LlmDiagnosticsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(invokeLlmSmoke).mockReset();
    vi.mocked(invokeLlmSmoke).mockResolvedValue(invocation);
    vi.mocked(getLlmReadiness).mockResolvedValue({ status: "ready", provider: "azure_openai", deployment_configured: true, model_capability: "responses_json_schema", error_code: null });
    vi.mocked(getLlmActivity).mockResolvedValue({ run_id: "run-1", invocations: [invocation] });
    vi.mocked(getLlmUsage).mockResolvedValue({ run_id: "run-1", invocation_count: 1, llm_calls: 1, retry_calls: 1, usage_recorded_calls: 1, usage_unavailable_calls: 0, input_tokens: 10, output_tokens: 5, total_tokens: 15, input_cost_usd: 0.00001, output_cost_usd: 0.00002, total_cost_usd: 0.00003, pricing_versions: ["pricing-v1"], by_phase: [{ key: "analysis", label: "Analysis", calls: 1, retry_calls: 1, usage_recorded_calls: 1, usage_unavailable_calls: 0, input_tokens: 10, output_tokens: 5, total_tokens: 15 }], by_stage: [{ key: "unassigned", label: "Run-level / unassigned", stage_id: null, calls: 1, retry_calls: 1, usage_recorded_calls: 1, usage_unavailable_calls: 0, input_tokens: 10, output_tokens: 5, total_tokens: 15 }], by_role: [{ key: "phase_proposer", label: "Phase proposer", calls: 1, retry_calls: 1, usage_recorded_calls: 1, usage_unavailable_calls: 0, input_tokens: 10, output_tokens: 5, total_tokens: 15 }], by_purpose: [{ key: "smoke_check", label: "Smoke check", calls: 1, retry_calls: 1, usage_recorded_calls: 1, usage_unavailable_calls: 0, input_tokens: 10, output_tokens: 5, total_tokens: 15 }], records: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it("renders provenance, token cost, and invokes through the typed backend contract", async () => {
    vi.mocked(invokeLlmSmoke).mockResolvedValue(invocation);
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} connectionStatus="open" />);
    expect(await screen.findByText("Estimated total cost")).toBeInTheDocument();
    expect(screen.getByText("LLM calls")).toBeInTheDocument();
    expect(screen.getByText("Recorded retries")).toBeInTheDocument();
    expect(screen.getByText("By phase")).toBeInTheDocument();
    expect(screen.getByText("By role")).toBeInTheDocument();
    expect(screen.getByText("By Angular stage")).toBeInTheDocument();
    expect(screen.getByText("By purpose")).toBeInTheDocument();
    expect(screen.getByText("$0.000030")).toBeInTheDocument();
    expect(screen.getByText("phase_proposer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run governed smoke check" }));
    await waitFor(() => expect(invokeLlmSmoke).toHaveBeenCalledWith(expect.objectContaining({ run_id: "run-1", expected_state_version: 2 })));
  });

  it("shows a stale state recovery message without advancing local workflow state", async () => {
    vi.mocked(getLlmActivity).mockResolvedValue({ run_id: "run-1", invocations: [] });
    vi.mocked(getLlmUsage).mockResolvedValue({ run_id: "run-1", invocation_count: 0, llm_calls: 0, retry_calls: 0, usage_recorded_calls: 0, usage_unavailable_calls: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, input_cost_usd: 0, output_cost_usd: 0, total_cost_usd: 0, pricing_versions: [], by_phase: [], by_stage: [], by_role: [], by_purpose: [], records: [] });
    vi.mocked(invokeLlmSmoke).mockRejectedValue(new ApiClientError("stale", 409));
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} connectionStatus="open" />);
    const button = await screen.findByRole("button", { name: "Run governed smoke check" });
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.getByText("Total tokens").closest("li")).toHaveTextContent("0");
    fireEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("run changed");
  });

  it("keeps readiness and usage visible when activity fails", async () => {
    vi.mocked(getLlmActivity).mockRejectedValue(new ApiClientError("activity failed", 500, "GET", "/activity", JSON.stringify({ correlation_id: "corr-activity" })));
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} />);
    expect(await screen.findByText("azure_openai")).toBeInTheDocument();
    expect(await screen.findByText("Activity: The backend could not load this diagnostics section.")).toBeInTheDocument();
    expect(screen.getByText("$0.000030")).toBeInTheDocument();
  });

  it("keeps activity visible when usage fails", async () => {
    vi.mocked(getLlmUsage).mockRejectedValue(new ApiClientError("usage failed", 500));
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} />);
    expect(await screen.findByText("phase_proposer")).toBeInTheDocument();
    expect(await screen.findByText("Usage: The backend could not load this diagnostics section.")).toBeInTheDocument();
    expect(screen.getByText("Usage unavailable")).toBeInTheDocument();
  });

  it("refreshes the new run and ignores the previous run response", async () => {
    let resolveFirst: ((response: LlmUsageResponse) => void) | undefined;
    const firstUsage = new Promise<LlmUsageResponse>((resolve) => { resolveFirst = resolve; });
    vi.mocked(getLlmActivity).mockImplementation(async (requestedRunId) => ({ run_id: requestedRunId, invocations: requestedRunId === "run-1" ? [invocation] : [] }));
    vi.mocked(getLlmUsage).mockImplementation((requestedRunId) => requestedRunId === "run-1" ? firstUsage : Promise.resolve(usageResponse("run-2", 99)));
    const { rerender } = render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} />);
    await waitFor(() => expect(getLlmUsage).toHaveBeenCalledWith("run-1"));

    rerender(<LlmDiagnosticsPanel runId="run-2" stateVersion={2} />);

    await waitFor(() => expect(getLlmUsage).toHaveBeenCalledWith("run-2"));
    await waitFor(() => expect(screen.getByText("Total tokens").closest("li")).toHaveTextContent("99"));
    resolveFirst?.(usageResponse("run-1", 1));
    await waitFor(() => expect(screen.getByText("Total tokens").closest("li")).toHaveTextContent("99"));
  });

  it("debounces rapid authoritative state updates into one refresh", async () => {
    const { rerender } = render(<LlmDiagnosticsPanel runId="run-1" stateVersion={1} />);
    rerender(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} />);
    rerender(<LlmDiagnosticsPanel runId="run-1" stateVersion={3} />);
    await screen.findByText("Estimated total cost");
    await waitFor(() => {
      expect(getLlmReadiness).toHaveBeenCalledTimes(1);
      expect(getLlmActivity).toHaveBeenCalledTimes(1);
      expect(getLlmUsage).toHaveBeenCalledTimes(1);
    });
  });

  it("leads with the invocation outcome and keeps provider metadata behind Response details", async () => {
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} connectionStatus="open" />);
    expect(await screen.findByRole("heading", { name: "Outcome: completed" })).toBeInTheDocument();
    expect(screen.getByText("azure_openai")).not.toBeVisible();
    fireEvent.click(screen.getByText("Response details"));
    expect(screen.getByText("azure_openai")).toBeVisible();
  });

  it("keeps smoke actions disabled while authoritative state is recovering", async () => {
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} connectionStatus="recovering" />);
    const smokeCheck = await screen.findByRole("button", { name: "Run governed smoke check" });
    expect(smokeCheck).toBeDisabled();
  });

  it("keeps the correlation identifier inside Response details", async () => {
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} connectionStatus="open" />);
    await screen.findByRole("heading", { name: "Outcome: completed" });
    expect(screen.getByText("Correlation ID:", { exact: false })).not.toBeVisible();
    fireEvent.click(screen.getByText("Response details"));
    expect(screen.getByText("Correlation ID:", { exact: false })).toBeVisible();
  });
});
