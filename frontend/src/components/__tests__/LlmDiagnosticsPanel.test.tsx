import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiClientError } from "@/api/client";
import { LlmDiagnosticsPanel } from "@/components/LlmDiagnosticsPanel";
import { getLlmActivity, getLlmReadiness, getLlmUsage, invokeLlmSmoke } from "@/api/llm";

vi.mock("@/api/llm", () => ({ getLlmActivity: vi.fn(), getLlmReadiness: vi.fn(), getLlmUsage: vi.fn(), invokeLlmSmoke: vi.fn() }));

const invocation = { invocation_id: "llm-1", run_id: "run-1", status: "completed" as const, role: "phase_proposer", task_type: "smoke_check", provider: "azure_openai", deployment_alias: "azure-openai", artifact_ids: ["artifact-usage"], artifact_checksums: { "artifact-usage": "sha256:usage" }, input_tokens: 10, output_tokens: 5, total_tokens: 15, input_cost_usd: 0.00001, output_cost_usd: 0.00002, total_cost_usd: 0.00003, retries: 1, latency_ms: 250, failure_code: null, state_version: 3, event_sequence: 4, idempotent_replay: false };

describe("LlmDiagnosticsPanel", () => {
  beforeEach(() => {
    vi.mocked(getLlmReadiness).mockResolvedValue({ status: "ready", provider: "azure_openai", deployment_configured: true, model_capability: "responses_json_schema", error_code: null });
    vi.mocked(getLlmActivity).mockResolvedValue({ run_id: "run-1", invocations: [invocation] });
    vi.mocked(getLlmUsage).mockResolvedValue({ run_id: "run-1", invocation_count: 1, input_tokens: 10, output_tokens: 5, total_tokens: 15, input_cost_usd: 0.00001, output_cost_usd: 0.00002, total_cost_usd: 0.00003, pricing_versions: ["pricing-v1"], records: [] });
  });

  it("renders provenance, token cost, and invokes through the typed backend contract", async () => {
    vi.mocked(invokeLlmSmoke).mockResolvedValue(invocation);
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} connectionStatus="open" />);
    expect(await screen.findByText("Estimated total cost")).toBeInTheDocument();
    expect(screen.getByText("$0.000030")).toBeInTheDocument();
    expect(screen.getByText("phase_proposer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run governed smoke check" }));
    await waitFor(() => expect(invokeLlmSmoke).toHaveBeenCalledWith(expect.objectContaining({ run_id: "run-1", expected_state_version: 2 })));
  });

  it("shows a stale state recovery message without advancing local workflow state", async () => {
    vi.mocked(getLlmActivity).mockResolvedValue({ run_id: "run-1", invocations: [] });
    vi.mocked(getLlmUsage).mockResolvedValue({ run_id: "run-1", invocation_count: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, input_cost_usd: 0, output_cost_usd: 0, total_cost_usd: 0, pricing_versions: [], records: [] });
    vi.mocked(invokeLlmSmoke).mockRejectedValue(new ApiClientError("stale", 409));
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} connectionStatus="open" />);
    fireEvent.click(await screen.findByRole("button", { name: "Run governed smoke check" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("run changed");
  });

  it("keeps readiness and usage visible when activity fails", async () => {
    vi.mocked(getLlmActivity).mockRejectedValue(new ApiClientError("activity failed", 500, "GET", "/activity", JSON.stringify({ correlation_id: "corr-activity" })));
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} />);
    expect(await screen.findByText("azure_openai")).toBeInTheDocument();
    expect(screen.getByText("Activity: The backend could not load this diagnostics section.")).toBeInTheDocument();
    expect(screen.getByText("$0.000030")).toBeInTheDocument();
  });

  it("keeps activity visible when usage fails", async () => {
    vi.mocked(getLlmUsage).mockRejectedValue(new ApiClientError("usage failed", 500));
    render(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} />);
    expect(await screen.findByText("phase_proposer")).toBeInTheDocument();
    expect(screen.getByText("Usage: The backend could not load this diagnostics section.")).toBeInTheDocument();
  });

  it("debounces rapid authoritative state updates into one refresh", async () => {
    const { rerender } = render(<LlmDiagnosticsPanel runId="run-1" stateVersion={1} />);
    rerender(<LlmDiagnosticsPanel runId="run-1" stateVersion={2} />);
    rerender(<LlmDiagnosticsPanel runId="run-1" stateVersion={3} />);
    await screen.findByText("Estimated total cost");
    expect(getLlmReadiness).toHaveBeenCalledTimes(1);
    expect(getLlmActivity).toHaveBeenCalledTimes(1);
    expect(getLlmUsage).toHaveBeenCalledTimes(1);
  });
});
