import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SourceSnapshotPanel } from "@/components/SourceSnapshotPanel";
import type { AuthoritativeRunStateDto, SourceSnapshotDto } from "@/types/generated/api";
import { createSourceSnapshot, getSourceSnapshot } from "@/api/snapshots";

vi.mock("@/api/snapshots", () => ({
  createSourceSnapshot: vi.fn(),
  getSourceSnapshot: vi.fn(),
}));

const state: AuthoritativeRunStateDto = {
  run_id: "run-1",
  status: "SOURCE_VALIDATION_RUNNING",
  run_phase: "PREFLIGHT_SNAPSHOT",
  phase_status: "running",
  approval_status: "approved",
  repair_status: "not_required",
  state_version: 2,
  preflight_id: "preflight-1",
  source_path: "C:/source",
  target_output_path: "C:/target",
  graph_thread_id: "thread-1",
  created_at: "2026-07-15T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
  artifacts: [],
  workflow_events: [],
};

const created: SourceSnapshotDto = {
  snapshot_id: "snapshot-1",
  run_id: "run-1",
  status: "created",
  source_path: "C:/source",
  snapshot_path: "C:/target/.migration-factory/runs/run-1/source-snapshot/snapshot-1",
  manifest_id: "manifest-1",
  fingerprint: "sha256:fingerprint",
  policy_version: "source-snapshot-policy-v1",
  file_count: 4,
  total_size_bytes: 2048,
  exclusions: [{ relative_path: "dist", reason: "excluded-directory", policy_version: "source-snapshot-policy-v1" }],
  git_metadata: {},
  artifacts: [{
    artifact_id: "artifact-manifest",
    run_id: "run-1",
    stage_id: null,
    artifact_type: "json",
    relative_path: "global/source-snapshots/snapshot-1/source_manifest.json",
    created_at: "2026-07-15T00:00:00Z",
    checksum: "sha256:artifact",
  }],
  state_version: 3,
  event_sequence: 2,
  idempotent_replay: false,
  error_code: null,
  error_message: null,
  created_at: "2026-07-15T00:00:00Z",
};

describe("SourceSnapshotPanel", () => {
  it("renders a subordinate heading when embedded in a pipeline stage", () => {
    render(<SourceSnapshotPanel runId="run-1" initialState={state} headingLevel={4} />);
    expect(screen.getByRole("heading", { name: "Immutable source snapshot", level: 4 })).toBeInTheDocument();
  });

  it("creates and renders authoritative snapshot evidence", async () => {
    vi.mocked(createSourceSnapshot).mockResolvedValue(created);
    vi.mocked(getSourceSnapshot).mockResolvedValue(created);

    render(<SourceSnapshotPanel runId="run-1" initialState={state} />);
    expect(screen.getByText("No source snapshot has been created for this run.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Create source snapshot" }));

    await waitFor(() => expect(screen.getByText("sha256:fingerprint")).toBeInTheDocument());
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Excluded paths: dist")).toBeInTheDocument();
    expect(screen.getByText("global/source-snapshots/snapshot-1/source_manifest.json")).toBeInTheDocument();
    expect(createSourceSnapshot).toHaveBeenCalledWith("run-1", expect.objectContaining({
      expected_state_version: 2,
      actor: "control-tower",
    }));
  });
});
