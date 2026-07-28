import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { decideG04, generateAnalysis, getAnalysis, retryAnalysis } from "@/api/analysis";
import { AnalysisReviewPanel } from "@/components/AnalysisReviewPanel";

vi.mock("@/api/analysis", () => ({ getAnalysis: vi.fn(), generateAnalysis: vi.fn(), retryAnalysis: vi.fn(), decideG04: vi.fn() }));
const packageData = { run_id: "run-1", artifact_set_checksum: "sha256:" + "a".repeat(64), deterministic_input_artifacts: [{ artifact_id: "fact-1", checksum: "sha256:" + "b".repeat(64) }], narrative: { summary: "Review the deterministic findings.", risk_groups: [{ name: "builder" }], unresolved_questions: ["Confirm package support"], evidence_confidence: "high", recommended_next_action: "Review G04", deterministic_input_checksum: "sha256:" + "a".repeat(64) }, proposer_output_checksum: "sha256:" + "d".repeat(64), model_provenance: { provider: "azure-openai", role: "phase_proposer" }, usage: { input_tokens: 10, output_tokens: 20, total_cost_usd: 0.001 }, prompt_version: "analysis_agent_v1", schema_version: "analysis-schema-registry-v1", reviewer: { decision: "accept", notes: ["Evidence is bounded."], risks: [], policy_concerns: [], confidence: "high", deterministic_input_checksum: "sha256:" + "a".repeat(64), proposer_output_checksum: "sha256:" + "d".repeat(64) }, reviewer_output_checksum: "sha256:" + "e".repeat(64), reviewer_provenance: { provider: "azure-openai", role: "phase_reviewer" }, reviewer_usage: { input_tokens: 5, output_tokens: 8, total_cost_usd: 0.0001 }, reviewer_prompt_version: "analysis_reviewer_v1", reviewer_schema_version: "analysis-schema-registry-v1", revision_count: 0, workspace_fingerprint: null, plan_version: null, review_status: "accepted" };
const response = { run_id: "run-1", analysis_id: "analysis-1", status: "completed", package: packageData, artifact_ids: ["g04-package"], artifact_checksums: { "g04-package": "sha256:" + "c".repeat(64) }, artifact_links: { "g04-package": "/api/v1/artifacts/g04-package" }, package_checksum: "sha256:" + "c".repeat(64), gate_id: "G04", gate_version: "g04-v1", gate_status: "pending", gate_decision: null, error_code: null, state_version: 4, event_sequence: 7, idempotent_replay: false } as const;
const props = { runId: "run-1", stateVersion: 4, connectionStatus: "open", artifacts: [{ artifact_id: "fact-1", checksum: "sha256:" + "b".repeat(64), run_id: "run-1", stage_id: null, artifact_type: "json" as const, relative_path: "facts.json", created_at: "now" }], workflowEvents: [{ event_type: "PARITY_BASELINE_COMPLETED", sequence: 1 }], refreshAuthoritativeState: vi.fn().mockResolvedValue(undefined) };

describe("AnalysisReviewPanel", () => {
  beforeEach(() => vi.clearAllMocks());
  it("renders split facts, interpretation, provenance, evidence, and G04 controls", async () => {
    vi.mocked(getAnalysis).mockResolvedValue(response as never);
    render(<AnalysisReviewPanel {...props} />);
    expect(await screen.findByText("Review the deterministic findings.")).toBeInTheDocument();
    expect(screen.getByText("Deterministic machine facts")).toBeInTheDocument(); expect(screen.getByText("AI interpretation")).toBeInTheDocument(); expect(screen.getAllByText(/azure-openai/)).toHaveLength(2); expect(screen.getByText("Phase Reviewer")).toBeInTheDocument(); expect(screen.getByRole("link", { name: "g04-package" })).toHaveAttribute("href", "/api/v1/artifacts/g04-package");
  });
  it("generates from registered artifacts and refreshes on stale conflict", async () => {
    vi.mocked(getAnalysis).mockRejectedValue(new ApiClientError("missing", 404)); vi.mocked(generateAnalysis).mockRejectedValue(new ApiClientError("stale", 409));
    render(<AnalysisReviewPanel {...props} />); await screen.findByText("No analysis package is available yet."); fireEvent.click(screen.getByRole("button", { name: "Start analysis" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("analysis state is stale"); expect(generateAnalysis).toHaveBeenCalledWith("run-1", expect.objectContaining({ expected_state_version: 4, idempotency_key: expect.any(String) }));
  });
  it("retries the exact failed analysis through the dedicated retry command", async () => {
    vi.mocked(getAnalysis).mockResolvedValue({ ...response, status: "failed", package: null, package_checksum: null, retryable: true, error_code: "ANALYSIS_PROVIDER_FAILED", failure_stage: "phase_proposer", attempt_history: [{ attempt: 1, status: "failed" }] } as never);
    vi.mocked(retryAnalysis).mockResolvedValue({ ...response, status: "in_progress", package: null, package_checksum: null } as never);
    render(<AnalysisReviewPanel {...props} />);
    const button = await screen.findByRole("button", { name: "Retry analysis" });
    fireEvent.click(button);
    expect(retryAnalysis).toHaveBeenCalledWith("run-1", expect.objectContaining({ failed_analysis_id: "analysis-1", expected_state_version: 4, reason: expect.any(String), idempotency_key: expect.any(String) }));
    expect(generateAnalysis).not.toHaveBeenCalled();
  });
  it("renders backend failure with a correlation ID", async () => {
    vi.mocked(getAnalysis).mockRejectedValue(new ApiClientError("failed", 500, "GET", "/analysis", JSON.stringify({ correlation_id: "corr-4" })));
    render(<AnalysisReviewPanel {...props} />); expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-4");
  });
  it("fails closed for blocked analysis and renders narrative content as text", async () => {
    vi.mocked(getAnalysis).mockResolvedValue({ ...response, status: "blocked", package: { ...packageData, narrative: { ...packageData.narrative, summary: "<img src=x onerror=alert(1)>" } }, error_code: "ANALYSIS_SCHEMA_INVALID" } as never);
    render(<AnalysisReviewPanel {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Analysis is blocked");
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
  it("requires a comment for approval with comment", async () => {
    vi.mocked(getAnalysis).mockResolvedValue(response as never); render(<AnalysisReviewPanel {...props} />); await screen.findByText("Review the deterministic findings."); fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "approve_with_comment" } }); fireEvent.click(screen.getByRole("button", { name: "Record G04 decision" })); expect(await screen.findByRole("alert")).toHaveTextContent("Add a comment"); expect(decideG04).not.toHaveBeenCalled();
  });
});
