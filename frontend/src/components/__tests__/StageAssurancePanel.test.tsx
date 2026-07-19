import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StageAssurancePanel } from "@/components/StageAssurancePanel";
import { ApiClientError } from "@/api/client";
import { getStageAssurance } from "@/api/stageAssurance";

vi.mock("@/api/stageAssurance", () => ({
  getStageAssurance: vi.fn(),
  submitG09Decision: vi.fn(),
  updateStageAssurance: vi.fn(),
}));

const response = {
  assurance_id: "assurance-1",
  run_id: "run-1",
  stage_id: "stage-1",
  status: "passed_with_manual_items",
  gates: [
    { gate_id: "gate-1", name: "install_static", label: "Install & static", status: "passed", checked_at: "2026-07-19T00:00:00Z", detail: null, artifact_ids: ["a1"], artifact_checksums: { "a1": "sha256:a" } },
    { gate_id: "gate-2", name: "test_suite", label: "Test suite", status: "manual_required", checked_at: null, detail: "Manual verification required", artifact_ids: [], artifact_checksums: {} },
  ],
  route_deltas: [{ route: "/home", type: "unchanged", previous_controller: null, current_controller: null, previous_template: null, current_template: null }],
  api_deltas: [{ endpoint: "/api/data", method: "GET", type: "unchanged", previous_proxy: null, current_proxy: null }],
  cards: [
    { card_id: "card-1", title: "Functional parity", status: "passed", summary: "All routes match", evidence_artifact_ids: ["a1"], proof_label: "machine_proven" },
  ],
  manual_items: [
    { item_id: "manual-1", description: "Verify custom webpack config", required: true, completed: false, completed_at: null, completed_by: null },
  ],
  artifact_ids: ["a1"],
  artifact_checksums: { "a1": "sha256:a" },
  g09_decision: null,
  state_version: 2,
  event_sequence: 3,
  idempotent_replay: false,
};

describe("StageAssurancePanel", () => {
  it("shows loading state initially", () => {
    vi.mocked(getStageAssurance).mockReturnValue(new Promise(() => {}));
    render(<StageAssurancePanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(screen.getByText("Loading assurance data...")).toBeInTheDocument();
  });

  it("renders gates, deltas, cards, and manual items", async () => {
    vi.mocked(getStageAssurance).mockResolvedValue(response);
    render(<StageAssurancePanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("Install & static")).toBeInTheDocument();
    expect(await screen.findByText("manual required")).toBeInTheDocument();
    expect(await screen.findByText("Functional parity")).toBeInTheDocument();
    expect(await screen.findByText("machine proven")).toBeInTheDocument();
    expect(await screen.findByText(/Verify custom webpack config/)).toBeInTheDocument();
    expect(await screen.findByText("Live assurance state")).toBeInTheDocument();
  });

  it("shows empty state when no assurance exists", async () => {
    vi.mocked(getStageAssurance).mockRejectedValue(new ApiClientError("not found", 404));
    render(<StageAssurancePanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("No assurance evaluation has been started.")).toBeInTheDocument();
  });

  it("shows error state on backend failure", async () => {
    vi.mocked(getStageAssurance).mockRejectedValue(new ApiClientError("server error", 500));
    render(<StageAssurancePanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("Stage assurance data could not be loaded.")).toBeInTheDocument();
  });
});
