import { fireEvent, render, screen, within } from "@testing-library/react";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";
import { useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
import { useTransformation } from "@/hooks/useTransformation";
import { makeArtifact, makeAuthoritativeRun, makeEvent } from "@/test/authoritativeFixtures";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";

const pipelineRender = vi.fn();

vi.mock("@/hooks/useAuthoritativeRun", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useAuthoritativeRun")>("@/hooks/useAuthoritativeRun");
  return { ...actual, useAuthoritativeRun: vi.fn() };
});
vi.mock("@/hooks/useTransformation", () => ({ useTransformation: vi.fn() }));
vi.mock("@/components/control-tower/PipelineSection", () => ({
  PipelineSection: ({ focusStage }: { focusStage?: string }) => {
    pipelineRender(focusStage);
    return <section aria-label="Pipeline workspace">{focusStage ? `Focused stage: ${focusStage}` : "Pipeline workspace"}</section>;
  },
}));
vi.mock("@/components/LlmDiagnosticsPanel", () => ({ LlmDiagnosticsPanel: () => <p>Provider diagnostics</p> }));
vi.mock("@/components/AssistantPanel", () => ({ AssistantDock: () => <button type="button">Open Assistant</button> }));
vi.mock("@/components/AuthoritativeRunCancellationPanel", () => ({ AuthoritativeRunCancellationPanel: () => <button type="button">Cancel run</button> }));

function transformationHook(overrides: Partial<ReturnType<typeof useTransformation>> = {}) {
  return {
    projection: null,
    executions: [],
    executionStatus: "idle" as const,
    status: "disabled" as const,
    refresh: vi.fn().mockResolvedValue(undefined),
    refreshError: null,
    loadError: null,
    ...overrides,
  };
}

function renderDashboard(
  run: AuthoritativeRunStateDto = makeAuthoritativeRun(),
  connection: ReturnType<typeof useAuthoritativeRun>["status"] = "open",
) {
  vi.mocked(useAuthoritativeRun).mockReturnValue({
    state: run,
    status: connection,
    error: null,
    refresh: vi.fn().mockResolvedValue(undefined),
  });
  return render(<AuthoritativeRunDashboard runId={run.run_id} initialState={run} />);
}

function pendingG06Run() {
  return makeAuthoritativeRun({
    state_version: 7,
    status: "WAITING_PLAN_APPROVAL",
    phase_status: "waiting_approval",
    approval_status: "pending",
    workflow_events: [
      makeEvent("RUN_CREATED", 1),
      makeEvent("G06_CREATED", 2, {
        payload: {
          gate_id: "G06",
          package_checksum: "sha256:g06",
          expected_state_version: 7,
          permitted_decisions: ["approved", "modification_requested", "rejected"],
        },
      }),
    ],
  });
}

function blockedTransformation(runId: string): TransformationProjection {
  return {
    run_id: runId,
    continuation_id: "continuation-1",
    stage_id: "stage-20-21",
    status: "blocked",
    current_node: "stage_transformation",
    state_version: 9,
    stage_status: "blocked",
    source_version: "20",
    target_version: "21",
    checkpoint_kind: null,
    workspace_fingerprint: "sha256:workspace",
    active_gate: null,
    active_gate_package_checksum: null,
    active_command_id: null,
    active_command_status: null,
    active_prompt_id: null,
    active_prompt_checksum: null,
    active_prompt_text: null,
    active_prompt_options: [],
    active_prompt_explanation: null,
    repair_attempt_id: null,
    repair_attempt_number: null,
    repair_status: null,
    repair_risk_level: null,
    repair_proposal_checksum: null,
    repair_review_checksum: null,
    repair_proposal_id: null,
    repair_base_checksum: null,
    repair_safe_diff: null,
    repair_review: null,
    repair_rationale: [],
    repair_apply_checksum: null,
    repair_validation_checksum: null,
    workflow_step: "stage_transformation",
    active_command_phase: null,
    stage_start_fingerprint: "sha256:workspace",
    repair_contract: null,
    dependency_operation: null,
    completed_transition_phases: [],
    repair_verification: null,
    dependency_closure: null,
    validation_results: {},
    active_error: { code: "POLICY_BLOCKED", message: "Policy blocked the stage." },
    historical_diagnostics: [],
    route_stages: [],
    sealed_chain_hash: null,
    last_error_code: null,
    last_error_message: null,
    runtime_profile_binding: null,
    cancel_requested_at: null,
  };
}

describe("AuthoritativeRunDashboard", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useTransformation).mockReturnValue(transformationHook());
  });

  it("exposes exactly the four Journey Command Center destinations", () => {
    renderDashboard();
    const navigation = screen.getByRole("navigation", { name: "Run sections" });

    expect(within(navigation).getByRole("button", { name: "Overview" })).toBeInTheDocument();
    expect(within(navigation).getByRole("button", { name: "Pipeline" })).toBeInTheDocument();
    expect(within(navigation).getByRole("button", { name: "Evidence" })).toBeInTheDocument();
    expect(within(navigation).getByRole("button", { name: "Diagnostics" })).toBeInTheDocument();
    expect(within(navigation).getAllByRole("button")).toHaveLength(4);
    expect(screen.queryByRole("button", { name: "Transformation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "LLM Diagnostics" })).not.toBeInTheDocument();
  });

  it("owns exactly one authoritative run hook and one disabled transformation hook", () => {
    const run = makeAuthoritativeRun({
      workflow_events: [makeEvent("RUN_CREATED", 1), makeEvent("NOT_TRANSFORMATION_CONTINUATION_CREATED", 99)],
    });

    renderDashboard(run);

    expect(useAuthoritativeRun).toHaveBeenCalledOnce();
    expect(useTransformation).toHaveBeenCalledOnce();
    expect(useTransformation).toHaveBeenCalledWith(run.run_id, { enabled: false, refreshKey: 0 });
  });

  it("enables transformation only from staged phase or exact transformation event membership", () => {
    const run = makeAuthoritativeRun({
      workflow_events: [
        makeEvent("RUN_CREATED", 1),
        makeEvent("G07_CREATED", 4),
        makeEvent("TRANSFORMATION_CONTINUATION_WAITING", 7),
        makeEvent("G07_CREATED_LOOKALIKE", 99),
      ],
    });

    renderDashboard(run);

    expect(useTransformation).toHaveBeenCalledWith(run.run_id, { enabled: true, refreshKey: 7 });
  });

  it("enables transformation for the staged-migration phase without guessed events", () => {
    const run = makeAuthoritativeRun({ run_phase: "STAGED_MIGRATION" });

    renderDashboard(run);

    expect(useTransformation).toHaveBeenCalledWith(run.run_id, { enabled: true, refreshKey: 0 });
  });

  it("highlights Pipeline for an action without changing the operator's active destination", () => {
    renderDashboard(pendingG06Run());
    const pipeline = screen.getByRole("button", { name: "Pipeline Action required" });

    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(pipeline).toHaveAttribute("data-action-required", "true");
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));

    expect(screen.getByRole("button", { name: "Evidence" })).toHaveAttribute("aria-current", "page");
    expect(pipeline).not.toHaveAttribute("aria-current");
  });

  it("navigates and focuses a stage only after the operator uses the current-action link", () => {
    renderDashboard(pendingG06Run());

    fireEvent.click(screen.getByRole("button", { name: "View in pipeline" }));

    expect(screen.getByRole("button", { name: "Pipeline Action required" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Pipeline workspace")).toHaveTextContent("Focused stage: plan");
  });

  it("mounts feature workspaces only for the active destination", () => {
    renderDashboard();

    expect(screen.queryByLabelText("Pipeline workspace")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));
    expect(screen.getByLabelText("Pipeline workspace")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));
    expect(screen.queryByLabelText("Pipeline workspace")).not.toBeInTheDocument();
  });

  it("renders one route heading, a skip link, human evidence, and closed technical details", () => {
    const run = makeAuthoritativeRun({
      artifacts: [makeArtifact({ relative_path: "00_job_setup/create_run_request.json" })],
    });

    renderDashboard(run);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveAccessibleName("source to source-angular-21");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#control-tower-content");
    expect(screen.getByText("Create run request")).toBeInTheDocument();
    expect(screen.getByText(run.run_id)).not.toBeVisible();
    expect(screen.getByText("Technical details").closest("details")).not.toHaveAttribute("open");
  });

  it("keeps confirmed context visible and disables fresh-state navigation during recovery", () => {
    renderDashboard(makeAuthoritativeRun(), "recovering");

    expect(screen.getByRole("heading", { name: "Authoritative state is refreshing" })).toBeInTheDocument();
    expect(screen.getByText(/Setup, Readiness, Production readiness/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Waiting for authoritative refresh" })).toBeDisabled();
  });

  it("withholds same-run transformation navigation after a background refresh failure until recovery", () => {
    const run = makeAuthoritativeRun({ run_phase: "STAGED_MIGRATION" });
    const projection = blockedTransformation(run.run_id);
    vi.mocked(useTransformation).mockReturnValue(transformationHook({
      projection,
      status: "ready",
      executionStatus: "ready",
      refreshError: "Background refresh failed; showing the last authoritative state.",
    }));
    const view = renderDashboard(run);

    expect(screen.getByRole("heading", { name: "Authoritative state is refreshing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Waiting for authoritative refresh" })).toBeDisabled();

    vi.mocked(useTransformation).mockReturnValue(transformationHook({
      projection,
      status: "ready",
      executionStatus: "ready",
      refreshError: null,
    }));
    view.rerender(<AuthoritativeRunDashboard runId={run.run_id} initialState={run} />);

    expect(screen.getByRole("heading", { name: "Transformation blocked" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View in pipeline" })).toBeEnabled();
  });

  it("presents reconnecting quietly without hiding the confirmed Overview", () => {
    renderDashboard(makeAuthoritativeRun(), "reconnecting");

    expect(screen.getByText("Connection lost · reconnecting…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("fails closed for incompatible run identifiers", () => {
    vi.mocked(useTransformation).mockReturnValue(transformationHook({
      status: "ready",
      executionStatus: "ready",
      projection: {
        run_id: "another-run",
        status: "running",
      } as TransformationProjection,
    }));

    renderDashboard();

    expect(screen.getByRole("heading", { name: "Authoritative state is refreshing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Waiting for authoritative refresh" })).toBeDisabled();
  });

  it("keeps Assistant subordinate after the primary navigation", () => {
    renderDashboard();

    expect(document.querySelector(".controlTowerAssistantSlot")).toContainElement(
      screen.getByRole("button", { name: "Open Assistant" }),
    );
    expect(screen.getAllByRole("button", { name: "Open Assistant" })).toHaveLength(1);
  });
});
