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
    const pipeline = screen.getByRole("button", { name: "Pipeline" });

    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(pipeline).toHaveAttribute("data-action-required", "true");
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));

    expect(screen.getByRole("button", { name: "Evidence" })).toHaveAttribute("aria-current", "page");
    expect(pipeline).not.toHaveAttribute("aria-current");
  });

  it("navigates and focuses a stage only after the operator uses the current-action link", () => {
    renderDashboard(pendingG06Run());

    fireEvent.click(screen.getByRole("button", { name: "View in pipeline" }));

    expect(screen.getByRole("button", { name: "Pipeline" })).toHaveAttribute("aria-current", "page");
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
