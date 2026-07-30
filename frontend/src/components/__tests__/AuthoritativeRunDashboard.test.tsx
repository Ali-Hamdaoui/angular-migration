import { fireEvent, render, screen } from "@testing-library/react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";

let planReviewShouldThrow = false;

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
vi.mock("@/components/PlanReviewPanel", () => ({ PlanReviewPanel: () => {
  if (planReviewShouldThrow) throw new Error("malformed review");
  return <h2>plan-review-panel</h2>;
} }));
vi.mock("@/components/TransformationPanel", () => ({ TransformationPanel: ({ onActionRequiredChange }: { onActionRequiredChange?: (required: boolean) => void }) => <div aria-label="mock-transformation-panel">transformation-panel<button type="button" onClick={() => onActionRequiredChange?.(true)}>Require Transformer action</button></div> }));
vi.mock("@/components/AssistantPanel", () => ({ AssistantDock: () => <button type="button">Open Assistant</button> }));

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
  beforeEach(() => {
    planReviewShouldThrow = false;
  });

  it("always exposes and mounts the dedicated Transformation destination", () => {
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={initialState} />);

    expect(screen.getByRole("button", { name: "Transformation" })).toBeInTheDocument();
    expect(screen.getByLabelText("mock-transformation-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Transformation" }));
    expect(screen.getByRole("heading", { name: "Transformation" })).toBeInTheDocument();
    expect(document.querySelector("[aria-labelledby='transformation-navigation-item']")).not.toHaveAttribute("hidden");
  });

  it("highlights and opens Transformation when its authoritative projection requires action", () => {
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={initialState} />);
    fireEvent.click(screen.getByText("Require Transformer action"));
    expect(screen.getByRole("button", { name: /Transformation/ })).toHaveAttribute("aria-current", "page");
    expect(document.querySelector("[aria-labelledby='transformation-navigation-item']")).not.toHaveAttribute("hidden");
  });

  it("keeps the dashboard rendered when the planning review panel throws", () => {
    planReviewShouldThrow = true;
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={{ ...initialState, workflow_events: [{ ...initialState.workflow_events[0], event_type: "MIGRATION_PLAN_CREATED" }] }} />);
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Planning & G06" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Planning review is temporarily unavailable");
    consoleError.mockRestore();
  });

  it("renders backend-owned state, event history, and evidence", () => {
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={initialState} />);

    expect(screen.getByText("Live · authoritative state")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));
    expect(screen.getByRole("listitem", { name: "Source intake: pending" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Source intake: pending" })).toHaveTextContent("pending");
    fireEvent.click(screen.getByRole("button", { name: "Files & Artifacts" }));
    expect(screen.getByText("00_job_setup/create_run_request.json")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "00_job_setup/create_run_request.json" })).toHaveAttribute("href", expect.stringContaining("artifact-create-request"));
    expect(screen.getByText("sha256:evidence")).toBeInTheDocument();
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
    events.push({ event_id: "event-install-output-after-success", run_id: initialState.run_id, stage_id: null, event_type: "COMMAND_OUTPUT_CHUNK", occurred_at: "2026-07-15T10:20:00Z", sequence: 99, payload: { chunk: "late buffered output" } });

    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={{ ...initialState, workflow_events: events }} />);
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));

    expect(screen.getByRole("listitem", { name: "Source intake: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Dependency installation: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Build: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Tests: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Lint: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "G03 readiness: completed" })).toBeInTheDocument();
  });

  it("does not attribute a qualification blocker to completed validation stages", () => {
    const events = [
      "BASELINE_BUILD_COMPLETED", "BASELINE_TESTS_COMPLETED", "BASELINE_LINT_COMPLETED",
      "BASELINE_FAILURES_FINGERPRINTED", "BASELINE_ROUTE_ANCHOR_CREATED", "BASELINE_BACKEND_ANCHOR_CREATED", "BASELINE_BLOCKED",
    ].map((event_type, index) => ({
      event_id: `event-${event_type}`, run_id: initialState.run_id, stage_id: null, event_type,
      occurred_at: `2026-07-15T12:${String(index).padStart(2, "0")}:00Z`, sequence: index + 2, payload: {},
    }));
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={{ ...initialState, workflow_events: events }} />);
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));

    expect(screen.getByRole("listitem", { name: "Build: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Tests: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Lint: completed" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Baseline qualification: blocked" })).toBeInTheDocument();
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

  it("keeps every destination mounted while switching presentation sections", () => {
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={{ ...initialState, workflow_events: [{ ...initialState.workflow_events[0], event_type: "DISCOVERY_COMPLETED" }] }} />);
    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(document.querySelector("[aria-labelledby='pipeline-navigation-item']")).toHaveAttribute("hidden");
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));
    expect(screen.getByRole("button", { name: "Pipeline" })).toHaveAttribute("aria-current", "page");
    expect(document.querySelector("[aria-labelledby='overview-navigation-item']")).toHaveAttribute("hidden");
  });

  it("opens and closes navigation without a backend action", () => {
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={initialState} />);
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(screen.getByRole("button", { name: "Close navigation" })).toBeInTheDocument();
    expect(document.querySelector(".controlTowerScrimOpen")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.querySelector(".controlTowerScrimOpen")).not.toBeInTheDocument();
  });

  it("shows exactly one actionable G03 panel and keeps it mounted when another stage is selected", () => {
    const events = [
      { ...initialState.workflow_events[0], event_type: "G02_APPROVED", sequence: 2 },
      { ...initialState.workflow_events[0], event_id: "install", event_type: "BASELINE_INSTALL_SUCCEEDED", sequence: 3 },
    ];
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={{ ...initialState, workflow_events: events }} />);
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));
    expect(document.querySelectorAll('[aria-label="Baseline qualification"]').length).toBe(1);
    expect(screen.getByRole("button", { name: "Qualify baseline" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Source snapshot/ }));
    expect(document.querySelectorAll('[aria-label="Baseline qualification"]').length).toBe(1);
    expect(screen.getByLabelText("G03 review")).toHaveAttribute("hidden");
  });
  it("renders one global Assistant launcher and no sidebar destination", () => {
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={initialState} />);
    expect(screen.queryByRole("button", { name: "Assistant" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Open Assistant" })).toHaveLength(1);
  });

  it("surfaces and navigates to the authoritative G02 review stage", () => {
    const event = { ...initialState.workflow_events[0], event_type: "G02_CREATED", sequence: 2 };
    render(<AuthoritativeRunDashboard runId={initialState.run_id} initialState={{ ...initialState, status: "SOURCE_VALIDATED", approval_status: "pending", workflow_events: [event] }} />);
    expect(screen.getByRole("button", { name: "Open G02 review" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open G02 review" }));
    expect(screen.getByRole("listitem", { name: "Source review & G02: action required" })).toBeInTheDocument();
    expect(screen.getByLabelText("G02 source integrity review")).toBeInTheDocument();
  });
});
