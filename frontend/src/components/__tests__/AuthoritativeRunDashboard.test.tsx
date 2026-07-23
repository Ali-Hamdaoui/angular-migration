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
vi.mock("@/components/AnalysisReviewPanel", () => ({ AnalysisReviewPanel: () => <h2>analysis-panel</h2> }));
vi.mock("@/components/FeasibilityPanel", () => ({ FeasibilityPanel: () => <h2>feasibility-panel</h2> }));
vi.mock("@/components/MigrationPlanPanel", () => ({ MigrationPlanPanel: () => <h2>plan-panel</h2> }));
vi.mock("@/components/PlanReviewPanel", () => ({ PlanReviewPanel: () => <h2>plan-review-panel</h2> }));

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

describe("AuthoritativeRunDashboard", () => {
  it("renders backend-owned state, event history, and evidence", () => {
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={initialState} />);

    expect(screen.getByText("Live · authoritative state")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "C:/source ? C:/target" })).toBeInTheDocument();
    expect(screen.getByText("RUN_CREATED")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Source intake: pending" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Source intake: pending" })).toHaveTextContent("pending");
    expect(screen.getByText("00_job_setup/create_run_request.json")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "00_job_setup/create_run_request.json" })).toHaveAttribute("href", expect.stringContaining("artifact-create-request"));
    expect(screen.getByText("sha256:evidence")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeInTheDocument();
    expect(screen.queryByRole("listitem", { name: /G03 readiness/ })).not.toBeInTheDocument();
  });

  it("renders the complete baseline timeline only after qualification evidence is authoritative", () => {
    const events = [
      "SOURCE_INTAKE_COMPLETED", "SNAPSHOT_CREATED", "G02_APPROVED", "EXECUTION_PROFILE_SELECTED",
      "BASELINE_WORKSPACE_READY", "BASELINE_INSTALL_SUCCEEDED", "BASELINE_BUILD_COMPLETED",
      "BASELINE_TESTS_COMPLETED", "BASELINE_LINT_COMPLETED", "BASELINE_QUALIFIED", "G03_CREATED",
    ].map((event_type, index) => ({
      event_id: `event-${event_type}`,
      run_id: initialState.run_id,
      stage_id: null,
      event_type,
      occurred_at: `2026-07-15T10:${String(index + 1).padStart(2, "0")}:00Z`,
      sequence: index + 2,
      payload: {},
    }));

    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={{ ...initialState, workflow_events: events }} />);

    expect(screen.getByRole("listitem", { name: "Source intake: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Dependency installation: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Build: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Tests: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Lint: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "G03 readiness: completed" })).toBeInTheDocument();
  });

  it("reveals each next review surface from its prerequisite event", () => {
    const events = ["DISCOVERY_COMPLETED", "G04_APPROVED", "G05_APPROVED", "MIGRATION_PLAN_CREATED"].map((event_type, index) => ({
      event_id: `event-${event_type}`, run_id: initialState.run_id, stage_id: null, event_type,
      occurred_at: `2026-07-15T11:0${index}:00Z`, sequence: index + 2, payload: {},
    }));
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={{ ...initialState, workflow_events: events }} />);
    expect(screen.getByText("analysis-panel")).toBeInTheDocument();
    expect(screen.getByText("feasibility-panel")).toBeInTheDocument();
    expect(screen.getByText("plan-panel")).toBeInTheDocument();
    expect(screen.getByText("plan-review-panel")).toBeInTheDocument();
  });
});
