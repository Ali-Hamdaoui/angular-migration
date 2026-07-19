import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StageValidationPanel } from "@/components/StageValidationPanel";
import { ApiClientError } from "@/api/client";
import { getStageValidation, startStageValidation } from "@/api/stageValidation";
import type { StageValidationResponse } from "@/types/stageValidation";

vi.mock("@/api/stageValidation", () => ({
  cancelStageValidation: vi.fn(),
  getStageValidation: vi.fn(),
  getStageValidationLogs: vi.fn(),
  startStageValidation: vi.fn(),
}));

const response = {
  validation_id: "val-1",
  run_id: "run-1",
  stage_id: "stage-1",
  status: "passed",
  steps: [
    { step_id: "step-1", name: "npm ci", kind: "install", status: "passed", started_at: "2026-07-19T00:00:00Z", completed_at: "2026-07-19T00:01:00Z", duration_ms: 60000, detail: null, error_code: null },
    { step_id: "step-2", name: "TypeScript check", kind: "static", status: "passed", started_at: "2026-07-19T00:01:00Z", completed_at: "2026-07-19T00:02:00Z", duration_ms: 60000, detail: null, error_code: null },
  ],
  diagnostics: [
    { diagnostic_id: "diag-1", file: "src/app.component.ts", code: "TS2322", severity: "error", message: "Type 'string' is not assignable to type 'number'", line: 42, column: 7, artifact_id: "artifact-1" },
  ],
  logs: ["npm ci output", "TypeScript check output"],
  artifact_ids: ["artifact-1"],
  artifact_checksums: { "artifact-1": "sha256:abc123" },
  state_version: 2,
  event_sequence: 3,
  idempotent_replay: false,
} as unknown as StageValidationResponse;

describe("StageValidationPanel", () => {
  it("shows loading state initially", () => {
    vi.mocked(getStageValidation).mockReturnValue(new Promise(() => {}));
    render(<StageValidationPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(screen.getByText("Loading stage validation state...")).toBeInTheDocument();
  });

  it("renders passed validation with steps and diagnostics", async () => {
    vi.mocked(getStageValidation).mockResolvedValue(response);
    render(<StageValidationPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("Live stage validation state")).toBeInTheDocument();
    expect(await screen.findByText("npm ci")).toBeInTheDocument();
    expect(await screen.findByText("TypeScript check")).toBeInTheDocument();
    expect(await screen.findByText("TS2322")).toBeInTheDocument();
    expect(await screen.findByText("Type 'string' is not assignable to type 'number'")).toBeInTheDocument();
    expect(screen.getByText(/state version 2/)).toBeInTheDocument();
  });

  it("shows empty state when no validation exists", async () => {
    vi.mocked(getStageValidation).mockRejectedValue(new ApiClientError("not found", 404));
    render(<StageValidationPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="connecting" />);
    expect(await screen.findByText("No stage validation has been started yet.")).toBeInTheDocument();
  });

  it("shows error state on backend failure", async () => {
    vi.mocked(getStageValidation).mockRejectedValue(new ApiClientError("server error", 500));
    render(<StageValidationPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("Stage validation evidence could not be loaded.")).toBeInTheDocument();
  });

  it("shows reconnecting status label", async () => {
    vi.mocked(getStageValidation).mockResolvedValue(response);
    render(<StageValidationPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="reconnecting" />);
    expect(await screen.findByText("Connection lost. Reconnecting...")).toBeInTheDocument();
  });

  it("starts validation with authoritative state version", async () => {
    vi.mocked(getStageValidation).mockRejectedValue(new ApiClientError("not found", 404));
    vi.mocked(startStageValidation).mockResolvedValue(response);
    render(<StageValidationPanel runId="run-1" stageId="stage-1" stateVersion={7} connectionStatus="open" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Run validation" })).toBeEnabled());
    screen.getByRole("button", { name: "Run validation" }).click();
    await waitFor(() => expect(startStageValidation).toHaveBeenCalledWith("run-1", "stage-1", expect.objectContaining({ expected_state_version: 7 })));
  });
});
