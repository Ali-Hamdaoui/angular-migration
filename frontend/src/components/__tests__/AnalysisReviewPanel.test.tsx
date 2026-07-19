import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { decideG04, generateAnalysis, getAnalysis } from "@/api/analysis";
import { AnalysisReviewPanel } from "@/components/AnalysisReviewPanel";

vi.mock("@/api/analysis", () => ({ getAnalysis: vi.fn(), generateAnalysis: vi.fn(), decideG04: vi.fn() }));
const packageData = { run_id: "run-1", artifact_set_checksum: "sha256:" + "a".repeat(64), deterministic_input_artifacts: [{ artifact_id: "fact-1", checksum: "sha256:" + "b".repeat(64) }], narrative: { summary: "Review the deterministic findings.", risk_groups: [{ name: "builder" }], unresolved_questions: ["Confirm package support"], evidence_confidence: "high", recommended_next_action: "Review G04", deterministic_input_checksum: "sha256:" + "a".repeat(64) }, model_provenance: { provider: "azure-openai", role: "phase_proposer" }, usage: { input_tokens: 10, output_tokens: 20, total_cost_usd: 0.001 }, prompt_version: "analysis_agent_v1", schema_version: "analysis-schema-registry-v1", workspace_fingerprint: null, plan_version: null, review_status: "pending" };
const response = { run_id: "run-1", analysis_id: "analysis-1", status: "completed", package: packageData, artifact_ids: ["g04-package"], artifact_checksums: { "g04-package": "sha256:" + "c".repeat(64) }, artifact_links: { "g04-package": "/api/v1/artifacts/g04-package" }, gate_id: "G04", gate_version: "g04-v1", gate_status: "pending", gate_decision: null, error_code: null, state_version: 4, event_sequence: 7, idempotent_replay: false } as const;
const props = { runId: "run-1", stateVersion: 4, connectionStatus: "open", artifacts: [{ artifact_id: "fact-1", checksum: "sha256:" + "b".repeat(64), run_id: "run-1", stage_id: null, artifact_type: "json" as const, relative_path: "facts.json", created_at: "now" }], workflowEvents: [], refreshAuthoritativeState: vi.fn().mockResolvedValue(undefined) };

describe("AnalysisReviewPanel", () => {
  it("renders split facts, interpretation, provenance, evidence, and G04 controls", async () => {
    vi.mocked(getAnalysis).mockResolvedValue(response as never);
    render(<AnalysisReviewPanel {...props} />);
    expect(await screen.findByText("Review the deterministic findings.")).toBeInTheDocument();
    expect(screen.getByText("Deterministic machine facts")).toBeInTheDocument(); expect(screen.getByText("AI interpretation")).toBeInTheDocument(); expect(screen.getByText("azure-openai")).toBeInTheDocument(); expect(screen.getByRole("link", { name: "g04-package" })).toHaveAttribute("href", "/api/v1/artifacts/g04-package");
  });
  it("generates from registered artifacts and refreshes on stale conflict", async () => {
    vi.mocked(getAnalysis).mockRejectedValue(new ApiClientError("missing", 404)); vi.mocked(generateAnalysis).mockRejectedValue(new ApiClientError("stale", 409));
    render(<AnalysisReviewPanel {...props} />); await screen.findByText("No analysis package is available yet."); fireEvent.click(screen.getByRole("button", { name: "Generate AI-assisted analysis" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("analysis state is stale"); expect(generateAnalysis).toHaveBeenCalledWith("run-1", expect.objectContaining({ expected_state_version: 4, prerequisite_artifacts: [{ artifact_id: "fact-1", checksum: "sha256:" + "b".repeat(64) }] }));
  });
  it("renders backend failure with a correlation ID", async () => {
    vi.mocked(getAnalysis).mockRejectedValue(new ApiClientError("failed", 500, "GET", "/analysis", JSON.stringify({ correlation_id: "corr-4" })));
    render(<AnalysisReviewPanel {...props} />); expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-4");
  });
  it("requires a comment for approval with comment", async () => {
    vi.mocked(getAnalysis).mockResolvedValue(response as never); render(<AnalysisReviewPanel {...props} />); await screen.findByText("Review the deterministic findings."); fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "approve_with_comment" } }); fireEvent.click(screen.getByRole("button", { name: "Record G04 decision" })); expect(await screen.findByRole("alert")).toHaveTextContent("Add a comment"); expect(decideG04).not.toHaveBeenCalled();
  });
});
