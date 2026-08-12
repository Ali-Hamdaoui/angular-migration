import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ApiClientError } from "@/api/client";
import type { TransformationProjection } from "@/types/transformation";
import { TransformationPanel } from "@/components/TransformationPanel";
import { decideTransformationGate, decideTransformationPrompt, requestRepairRevision } from "@/api/transformation";

vi.mock("@/api/transformation", () => ({
  decideTransformationGate: vi.fn(),
  decideTransformationPrompt: vi.fn(),
  cancelTransformation: vi.fn(),
  requestRepairRevision: vi.fn(),
  rejectRepair: vi.fn(),
  restartTransformation: vi.fn(),
}));
vi.mock("@/components/LogViewer", () => ({
  LiveCommandLogViewer: ({ executionId }: { executionId: string }) => <div>logs:{executionId}</div>,
}));

const baseProjection: TransformationProjection = {
  run_id: "run-1",
  continuation_id: "transform-1",
  stage_id: "stage-1",
  status: "waiting_gate",
  current_node: "wait_gate",
  state_version: 3,
  stage_status: "preparing",
  source_version: "18.x",
  target_version: "19.x",
  checkpoint_kind: "pre_bootstrap",
  workspace_fingerprint: "sha256:workspace",
  active_gate: "G07",
  active_gate_package_checksum: "sha256:package",
  active_command_id: null,
  active_command_status: null,
  active_prompt_id: null,
  active_prompt_checksum: null,
  active_prompt_text: null,
  active_prompt_options: [],
  active_prompt_explanation: null,
  repair_attempt_id: null,
  repair_attempt_number: null,
  repair_parent_attempt_id: null,
  repair_status: null,
  repair_risk_level: null,
  repair_proposal_checksum: null,
  repair_review_checksum: null,
  repair_proposal_id: null,
  repair_base_checksum: null,
  repair_diff_artifact_id: null,
  repair_diff_checksum: null,
  repair_proposal_operations: [],
  repair_safe_diff: null,
  repair_review: null,
  repair_rationale: [],
  repair_apply_checksum: null,
  repair_validation_checksum: null,
  workflow_step: "stage_workspace_ready",
  active_command_phase: null,
  stage_start_fingerprint: "sha256:workspace",
  repair_contract: null,
  dependency_operation: null,
  completed_transition_phases: [],
  repair_verification: null,
  dependency_closure: null,
  validation_results: {
    npm_ci: { status: "pending", execution_id: null, command_status: null },
    build: { status: "pending", execution_id: null, command_status: null },
    test: { status: "pending", execution_id: null, command_status: null },
  },
  active_error: null,
  historical_diagnostics: [],
  route_stages: [{ stage_id: "stage-1", source_version: "18.x", target_version: "19.x", status: "preparing" }],
  sealed_chain_hash: null,
  last_error_code: null,
  last_error_message: null,
  runtime_profile_binding: null,
  cancel_requested_at: null,
};

const refreshTransformation = vi.fn().mockResolvedValue(undefined);
const refreshAuthoritativeState = vi.fn().mockResolvedValue(undefined);

function renderPanel(
  projection: TransformationProjection | null = baseProjection,
  projectionStatus: "disabled" | "loading" | "ready" | "empty" | "failed" = projection ? "ready" : "empty",
) {
  return render(<TransformationPanel
    runId="run-1"
    projection={projection}
    projectionStatus={projectionStatus}
    executions={[]}
    executionStatus="ready"
    workflowEvents={[]}
    artifacts={[]}
    refreshTransformation={refreshTransformation}
    refreshAuthoritativeState={refreshAuthoritativeState}
  />);
}

describe("TransformationPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(requestRepairRevision).mockReset();
    refreshTransformation.mockResolvedValue(undefined);
    refreshAuthoritativeState.mockResolvedValue(undefined);
    vi.mocked(decideTransformationGate).mockResolvedValue({});
    vi.mocked(decideTransformationPrompt).mockResolvedValue({});
  });

  it("renders shell-owned projection props without opening a transformation request", async () => {
    renderPanel();
    expect(await screen.findByRole("heading", { name: /18.x/ })).toBeInTheDocument();
    expect(screen.queryByText("Loading authoritative Transformer state")).not.toBeInTheDocument();
  });

  it.each([
    ["loading", null, "Loading authoritative Transformer state"],
    ["empty", null, "Transformer continuation has not been created"],
    ["failed", null, "Transformer state unavailable"],
  ] as const)("renders a truthful %s state", (status, projection, text) => {
    renderPanel(projection, status);
    expect(screen.getByText(new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))).toBeInTheDocument();
  });

  it("renders blocked projection without inventing a completion", () => {
    renderPanel({ ...baseProjection, status: "blocked", active_gate: null, active_gate_package_checksum: null });
    expect(screen.getAllByText("Blocked").length).toBeGreaterThan(0);
    expect(screen.getByText(/No unresolved CLI prompt/)).toBeInTheDocument();
  });

  it("renders a waiting prompt and submits only the selected backend option", async () => {
    renderPanel({
      ...baseProjection,
      status: "waiting_prompt",
      active_gate: null,
      active_gate_package_checksum: null,
      active_prompt_id: "prompt-1",
      active_prompt_checksum: "sha256:prompt",
      active_prompt_text: "Choose migration option",
      active_prompt_options: [{ option_id: "yes", label: "Yes" }],
    });
    fireEvent.click(await screen.findByRole("button", { name: "Yes" }));
    await waitFor(() => expect(decideTransformationPrompt).toHaveBeenCalledWith("run-1", "prompt-1", expect.objectContaining({
      expected_state_version: 3,
      prompt_checksum: "sha256:prompt",
      selected_option_id: "yes",
    })));
  });

  it("renders active command activity and execution history from shell props", () => {
    render(<TransformationPanel
      runId="run-1"
      projection={{ ...baseProjection, status: "waiting_command", active_gate: null, active_command_id: "command-1", active_command_status: "running" }}
      projectionStatus="ready"
      executions={[{ execution_id: "command-1", run_id: "run-1", command_name: "angular-update", status: "running", started_at: null, completed_at: null, exit_code: null, stdout_artifact_id: null, stderr_artifact_id: null, artifact_ids: [] } as never]}
      executionStatus="ready"
      workflowEvents={[]}
      artifacts={[]}
      refreshTransformation={refreshTransformation}
      refreshAuthoritativeState={refreshAuthoritativeState}
    />);
    expect(screen.getByText("logs:command-1")).toBeInTheDocument();
    expect(screen.getByText("Command in flight")).toBeInTheDocument();
  });

  it.each([
    ["G11", "Repair validation acceptance", /approve repair validation/i, "sha256:g11"],
    ["G12", "Stage-completion acceptance", /approve stage completion/i, "sha256:g12"],
  ] as const)("renders actionable %s with shared gate vocabulary", async (gate, heading, button, checksum) => {
    renderPanel({ ...baseProjection, active_gate: gate, active_gate_package_checksum: checksum });
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: button });
    expect(approve).toBeEnabled();
    fireEvent.click(approve);
    await waitFor(() => expect(decideTransformationGate).toHaveBeenCalledWith("run-1", gate, expect.objectContaining({
      expected_state_version: 3,
      package_checksum: checksum,
      workspace_fingerprint: "sha256:workspace",
      decision: "approve",
      idempotency_key: expect.any(String),
      correlation_id: expect.any(String),
    })));
  });

  it("refreshes transformation and authoritative state after a gate decision", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => {
      expect(refreshTransformation).toHaveBeenCalledTimes(1);
      expect(refreshAuthoritativeState).toHaveBeenCalledTimes(1);
    });
  });

  it("submits the current repair bindings and preserves the exact human instruction", async () => {
    const baseChecksum = `sha256:${"4".repeat(64)}`;
    vi.mocked(requestRepairRevision).mockResolvedValue({
      attempt_id: "repair-4",
      status: "evidence_frozen",
      idempotent_replay: false,
    });
    renderPanel({
      ...baseProjection,
      active_gate: "G10",
      active_gate_package_checksum: "sha256:g10",
      repair_attempt_id: "repair-3",
      repair_attempt_number: 3,
      repair_status: "waiting_g10",
      repair_proposal_id: "proposal-3",
      repair_base_checksum: baseChecksum,
      repair_safe_diff: "diff evidence",
      repair_review: {
        decision: "accept",
        findings: [],
        policy_checks: [],
        risk_assessment: "Low risk",
        required_validation_targets: ["build"],
        limitations: [],
      },
    });

    fireEvent.change(screen.getByRole("textbox", { name: "Revision instructions" }), {
      target: { value: "  Handle empty values without changing behavior  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Request changes" }));

    await waitFor(() => expect(requestRepairRevision).toHaveBeenCalledWith(
      "run-1",
      "repair-3",
      {
        attempt_id: "repair-3",
        proposal_id: "proposal-3",
        base_checksum: baseChecksum,
        instruction: "  Handle empty values without changing behavior  ",
        idempotency_key: expect.any(String),
      },
    ));
  });

  it("shows structured repair validation details and correlation id", async () => {
    const baseChecksum = `sha256:${"5".repeat(64)}`;
    vi.mocked(requestRepairRevision).mockRejectedValue(new ApiClientError(
      "rejected",
      422,
      "POST",
      "/revisions",
      JSON.stringify({
        error_code: "validation_error",
        message: "Request validation failed.",
        correlation_id: "corr-1",
        details: {
          errors: [{ loc: ["body", "instruction"], msg: "filesystem paths are forbidden" }],
        },
      }),
    ));
    renderPanel({
      ...baseProjection,
      status: "waiting_repair_revision",
      current_node: "review_repair",
      active_gate: null,
      active_gate_package_checksum: null,
      repair_attempt_id: "repair-3",
      repair_attempt_number: 3,
      repair_status: "request_changes",
      repair_proposal_id: "proposal-3",
      repair_base_checksum: baseChecksum,
    });

    fireEvent.change(screen.getByRole("textbox", { name: "Revision instructions" }), {
      target: { value: "Revise the affected configuration" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Request changes" }));

    const alert = (await screen.findByText(/body\.instruction: filesystem paths are forbidden/)).closest("[role='alert']");
    expect(alert).not.toBeNull();
    expect(alert).toHaveTextContent("body.instruction: filesystem paths are forbidden");
    expect(alert).toHaveTextContent("Correlation ID: corr-1");
    expect(alert).toHaveTextContent("Error code: validation_error");
    expect(screen.getByRole("textbox", { name: "Revision instructions" })).toHaveValue("Revise the affected configuration");
  });

  it("groups each repair explanation with the decision it enables", () => {
    renderPanel({
      ...baseProjection,
      active_gate: "G10",
      active_gate_package_checksum: "sha256:g10",
      repair_attempt_id: "repair-3",
      repair_attempt_number: 3,
      repair_status: "waiting_g10",
      repair_proposal_checksum: "sha256:proposal",
      repair_proposal_id: "proposal-3",
      repair_base_checksum: `sha256:${"6".repeat(64)}`,
      repair_safe_diff: "diff evidence",
      repair_review: {
        decision: "request_changes",
        findings: ["One unresolved concern"],
        policy_checks: [],
        risk_assessment: "Medium risk",
        required_validation_targets: ["build"],
        limitations: [],
      },
    });

    const overrideDecision = screen.getByRole("group", { name: "Approve despite Reviewer concerns" });
    expect(within(overrideDecision).getByRole("textbox", { name: "Override comment" })).toHaveAttribute(
      "aria-describedby",
      "repair-override-help",
    );
    expect(within(overrideDecision).getByRole("button", { name: "Approve despite Reviewer concerns" })).toBeDisabled();

    const revisionDecision = screen.getByRole("group", { name: "Request changes" });
    expect(within(revisionDecision).getByRole("textbox", { name: "Revision instructions" })).toHaveAttribute(
      "aria-describedby",
      "repair-revision-help",
    );
    expect(within(revisionDecision).getByRole("button", { name: "Request changes" })).toBeDisabled();
  });

  it("fails closed when a pending gate is missing package or workspace bindings", () => {
    renderPanel({ ...baseProjection, active_gate: "G11", active_gate_package_checksum: null });
    expect(screen.getByText(/lacks the backend package checksum or workspace fingerprint/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve repair validation/i })).not.toBeInTheDocument();
  });

  it("rejects a non-transformation gate even when its bindings look complete", () => {
    renderPanel({ ...baseProjection, active_gate: "G03", active_gate_package_checksum: "sha256:g03" });
    expect(screen.getByText("This decision type is unsupported by the frontend.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(decideTransformationGate).not.toHaveBeenCalled();
  });

  it("leads with the current action and keeps technical details collapsed", () => {
    renderPanel();
    const headings = screen.getAllByRole("heading");
    const actionIndex = headings.findIndex((heading) => heading.textContent === "Stage-start acceptance");
    const stageIndex = headings.findIndex((heading) => heading.textContent === "Migration stages");
    expect(actionIndex).toBeGreaterThanOrEqual(0);
    expect(stageIndex).toBeGreaterThan(actionIndex);
    expect(screen.getAllByText("Technical details").every((summary) => !summary.closest("details")?.hasAttribute("open"))).toBe(true);
  });
});
