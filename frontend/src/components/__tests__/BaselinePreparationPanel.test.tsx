import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { BaselinePreparationPanel } from "@/components/BaselinePreparationPanel";
import { createBaselineWorkspace, getBaseline } from "@/api/baseline";
import type { BaselineResponse } from "@/types/generated/api";

vi.mock("@/api/baseline", () => ({
  getBaseline: vi.fn(),
  createBaselineWorkspace: vi.fn(),
  prequalifyBaseline: vi.fn(),
  authorizeBaselineInstall: vi.fn(),
}));

const state = { run_id: "run-1", status: "SOURCE_VALIDATED", run_phase: "BASELINE", phase_status: "running", approval_status: "approved", state_version: 4, preflight_id: "p1", source_path: "C:/source", target_output_path: "C:/target", graph_thread_id: "thread", created_at: "2026-01-01", updated_at: "2026-01-01", artifacts: [], workflow_events: [] } as never;
const workspace = { run_id: "run-1", status: "workspace_ready", policy_version: "baseline-prequalification-v1", snapshot_id: "snapshot-1", sandbox_path: "C:/output/.migration-factory/runs/run-1/baseline-sandbox", input_fingerprint: "sha256:input", sandbox_fingerprint: "sha256:sandbox", package: null, lockfile: null, sources: [], scripts: [], registry: null, blockers: [], warnings: [], authorization_status: "not_authorized", checksum: "sha256:workspace", artifact_ids: ["artifact-1"], state_version: 5, event_sequence: 2, idempotent_replay: false } as unknown as BaselineResponse;

describe("BaselinePreparationPanel", () => {
  it("creates the sandbox from the empty state and shows backend evidence", async () => {
    vi.mocked(getBaseline).mockRejectedValue(new ApiClientError("missing", 404));
    vi.mocked(createBaselineWorkspace).mockResolvedValue(workspace);
    render(<BaselinePreparationPanel runId="run-1" initialState={state} />);

    expect(await screen.findByText("No baseline sandbox has been created.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create baseline sandbox" }));
    await waitFor(() => expect(createBaselineWorkspace).toHaveBeenCalledWith("run-1", expect.objectContaining({ expected_state_version: 4, actor: "control-tower" })));
    expect(await screen.findByText("C:/output/.migration-factory/runs/run-1/baseline-sandbox")).toBeInTheDocument();
    expect(screen.getByText("1 immutable evidence artifacts")).toBeInTheDocument();
  });

  it("renders authoritative blockers", async () => {
    vi.mocked(getBaseline).mockResolvedValue({ ...workspace, status: "blocked", blockers: ["NPM_LOCKFILE_MISSING"], artifact_ids: [] } as never);
    render(<BaselinePreparationPanel runId="run-1" initialState={state} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("NPM_LOCKFILE_MISSING");
  });
});
