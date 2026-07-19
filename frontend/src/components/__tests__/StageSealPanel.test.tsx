import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StageSealPanel } from "@/components/StageSealPanel";
import { ApiClientError } from "@/api/client";
import { getStageSeal } from "@/api/stageSeal";

vi.mock("@/api/stageSeal", () => ({
  getStageSeal: vi.fn(),
  startCopyForward: vi.fn(),
  submitG12Decision: vi.fn(),
  submitStageSealRequest: vi.fn(),
}));

const response = {
  seal_id: "seal-1",
  run_id: "run-1",
  stage_id: "stage-1",
  status: "sealed",
  completeness: {
    status: "passed",
    checks: [
      { check_id: "check-1", name: "All artifacts registered", status: "passed", detail: "12 artifacts" },
      { check_id: "check-2", name: "No pending manual items", status: "passed", detail: null },
    ],
  },
  fingerprint: {
    fingerprint: "sha256:output-fingerprint",
    algorithm: "sha256",
    asset_count: 42,
    total_size_bytes: 1048576,
    created_at: "2026-07-19T00:00:00Z",
  },
  copy_forward: {
    status: "completed",
    source_stage_id: "stage-1",
    target_stage_id: "stage-2",
    copied_artifact_count: 8,
    copied_artifact_ids: ["artifact-1", "artifact-2"],
    detail: "Copy completed successfully",
  },
  artifact_ids: ["artifact-1"],
  artifact_checksums: { "artifact-1": "sha256:abc" },
  g12_decision: "APPROVED",
  state_version: 3,
  event_sequence: 4,
  idempotent_replay: false,
};

describe("StageSealPanel", () => {
  it("shows loading state initially", () => {
    vi.mocked(getStageSeal).mockReturnValue(new Promise(() => {}));
    render(<StageSealPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(screen.getByText("Loading seal state...")).toBeInTheDocument();
  });

  it("renders completeness checks, fingerprint, G12 decision, and copy-forward", async () => {
    vi.mocked(getStageSeal).mockResolvedValue(response);
    render(<StageSealPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("All artifacts registered")).toBeInTheDocument();
    expect(await screen.findByText(/sha256:output-fingerprint/)).toBeInTheDocument();
    expect(await screen.findByText("APPROVED")).toBeInTheDocument();
    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(await screen.findByText("Live seal state")).toBeInTheDocument();
  });

  it("shows empty state when no seal exists", async () => {
    vi.mocked(getStageSeal).mockRejectedValue(new ApiClientError("not found", 404));
    render(<StageSealPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("No seal has been started yet.")).toBeInTheDocument();
  });

  it("shows error state on backend failure", async () => {
    vi.mocked(getStageSeal).mockRejectedValue(new ApiClientError("server error", 500));
    render(<StageSealPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("Stage seal data could not be loaded.")).toBeInTheDocument();
  });
});
