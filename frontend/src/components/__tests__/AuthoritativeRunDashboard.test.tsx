import { render, screen } from "@testing-library/react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";

vi.mock("@/hooks/useAuthoritativeRun", () => ({
  useAuthoritativeRun: (_runId: string, initialState: AuthoritativeRunStateDto) => ({
    state: initialState,
    status: "open",
    error: null,
    refresh: vi.fn(),
  }),
}));

const initialState: AuthoritativeRunStateDto = {
  run_id: "run-authoritative-1",
  status: "CREATED",
  run_phase: "PREFLIGHT_SNAPSHOT",
  phase_status: "running",
  approval_status: "approved",
  repair_status: "not_required",
  state_version: 2,
  preflight_id: "preflight-1",
  source_path: "C:/source",
  target_output_path: "C:/target",
  graph_thread_id: "source-intake-run-authoritative-1",
  created_at: "2026-07-15T10:00:00Z",
  updated_at: "2026-07-15T10:00:01Z",
  artifacts: [{
    artifact_id: "artifact-create-request",
    run_id: "run-authoritative-1",
    stage_id: null,
    artifact_type: "json",
    relative_path: "00_job_setup/create_run_request.json",
    created_at: "2026-07-15T10:00:00Z",
    checksum: "sha256:evidence",
  }],
  workflow_events: [{
    event_id: "event-created",
    run_id: "run-authoritative-1",
    stage_id: null,
    event_type: "RUN_CREATED",
    occurred_at: "2026-07-15T10:00:00Z",
    sequence: 1,
    payload: { graph_thread_id: "source-intake-run-authoritative-1" },
  }],
};

const migrationState = { stages: [{ stage_id: "stage-1", status: "RUNNING", source_angular_version: "17.0.0", target_angular_version: "18.0.0" }] } as never;

describe("AuthoritativeRunDashboard", () => {
  it("renders backend-owned state, event history, and evidence", () => {
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={initialState} initialMigrationState={migrationState} />);

    expect(screen.getByText("Live ? authoritative state")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "C:/source ? C:/target" })).toBeInTheDocument();
    expect(screen.getByText("RUN_CREATED")).toBeInTheDocument();
    expect(screen.getByText("00_job_setup/create_run_request.json")).toBeInTheDocument();
    expect(screen.getByText("sha256:evidence")).toBeInTheDocument();
    expect(screen.getByText("Angular Update")).toBeInTheDocument();
  });
});
