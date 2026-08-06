import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiClientError } from "@/api/client";
import { TransformationPanel } from "@/components/TransformationPanel";
import { listCommandExecutions } from "@/api/commands";
import {
  decideTransformationGate,
  decideTransformationPrompt,
  getTransformation,
  rejectRepair,
  requestRepairRevision,
} from "@/api/transformation";

vi.mock("@/api/transformation", () => ({
  getTransformation: vi.fn(),
  decideTransformationGate: vi.fn(),
  decideTransformationPrompt: vi.fn(),
  cancelTransformation: vi.fn(),
  requestRepairRevision: vi.fn(),
  rejectRepair: vi.fn(),
  restartTransformation: vi.fn(),
}));
vi.mock("@/api/commands", () => ({
  listCommandExecutions: vi.fn(),
}));
vi.mock("@/components/LogViewer", () => ({
  LiveCommandLogViewer: ({ executionId }: { executionId: string }) => <div>logs:{executionId}</div>,
}));

const projection = {
  run_id: "run-1",
  continuation_id: "transform-1",
  stage_id: "stage-1",
  status: "waiting_gate",
  current_node: "wait_g07",
  state_version: 3,
  stage_status: "preparing",
  source_version: "18.x",
  target_version: "19.x",
  checkpoint_kind: "pre_bootstrap",
  workspace_fingerprint: "sha256:workspace",
  active_gate: "G07",
  active_gate_package_checksum: "sha256:g07",
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

const refreshAuthoritativeState = vi.fn().mockResolvedValue(undefined);

function event(event_type: string, sequence: number, payload = {}) {
  return { event_id: `${event_type}-${sequence}`, run_id: "run-1", stage_id: "stage-1", event_type, occurred_at: "2026-07-30T10:00:00Z", sequence, payload };
}

function renderPanel(overrides: Record<string, unknown> = {}) {
  return render(<TransformationPanel
    runId="run-1"
    workflowEvents={[]}
    artifacts={[]}
    authoritativeStatus="PLANNING"
    authoritativePhase="PLANNING"
    authoritativeStateVersion={12}
    refreshAuthoritativeState={refreshAuthoritativeState}
    {...overrides}
  />);
}

describe("TransformationPanel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(listCommandExecutions).mockResolvedValue({ run_id: "run-1", executions: [], total: 0 });
    refreshAuthoritativeState.mockResolvedValue(undefined);
  });

  it("keeps the pre-G06 state reachable and projects authoritative prerequisites", async () => {
    vi.mocked(getTransformation).mockRejectedValue(new ApiClientError("missing", 404));
    renderPanel({ workflowEvents: [event("G06_CREATED", 1)] });

    expect(await screen.findByRole("heading", { name: "Transformer continuation has not been created" })).toBeInTheDocument();
    expect(screen.getByText("Planning evidence")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("displays the authoritative Transformer continuation after accepted G06", async () => {
    vi.mocked(getTransformation).mockResolvedValue(projection);
    renderPanel({ workflowEvents: [event("G06_APPROVED", 1), event("TRANSFORMATION_CONTINUATION_CREATED", 2)] });
    expect((await screen.findAllByText(/Continuation ID: transform-1/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Stage-start approval" })).toBeInTheDocument();
  });

  it("projects a running command, logs, workspace, preflight, and current step", async () => {
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "waiting_command",
      current_node: "bootstrap_install",
      active_gate: null,
      active_gate_package_checksum: null,
      active_command_id: "command-1",
      active_command_status: "running",
    });
    renderPanel({ workflowEvents: [event("STAGE_INPUT_CHECKPOINT_CREATED", 1), event("COMPATIBILITY_PREFLIGHT_PASSED", 2)] });

    expect(await screen.findByRole("heading", { name: "18.x → 19.x" })).toBeInTheDocument();
    expect(screen.getAllByText(/Workflow node: bootstrap_install/).length).toBeGreaterThan(0);
    expect(screen.getByText("logs:command-1")).toBeInTheDocument();
    expect(screen.getAllByText("sha256:workspace", { exact: false }).length).toBeGreaterThan(0);
  });

  it("submits G07 once with the current version, package, fingerprint, and refreshes both projections", async () => {
    let resolveDecision!: (value: object) => void;
    vi.mocked(getTransformation).mockResolvedValue(projection);
    vi.mocked(decideTransformationGate).mockImplementation(() => new Promise((resolve) => { resolveDecision = resolve; }));
    renderPanel();
    const approve = await screen.findByRole("button", { name: "Approve" });

    fireEvent.click(approve);
    fireEvent.click(approve);
    expect(decideTransformationGate).toHaveBeenCalledTimes(1);
    expect(decideTransformationGate).toHaveBeenCalledWith("run-1", "G07", expect.objectContaining({
      expected_state_version: 3,
      package_checksum: "sha256:g07",
      workspace_fingerprint: "sha256:workspace",
      decision: "approve",
    }));
    resolveDecision({});

    await waitFor(() => expect(refreshAuthoritativeState).toHaveBeenCalledTimes(1));
    expect(getTransformation).toHaveBeenCalledTimes(2);
  });

  it("renders the Azure explanation as text and submits only the selected CLI option", async () => {
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "waiting_prompt",
      active_gate: null,
      active_gate_package_checksum: null,
      active_prompt_id: "prompt-1",
      active_prompt_checksum: "sha256:prompt",
      active_prompt_text: "<script>Choose migration</script>",
      active_prompt_options: [{ option_id: "yes", label: "Yes" }],
      active_prompt_explanation: {
        summary: "Angular needs a decision.",
        option_effects: ["Yes reconstructs and retries."],
        risk_note: "Review the migration.",
        source: "azure_openai",
      },
    });
    vi.mocked(decideTransformationPrompt).mockResolvedValue({});
    renderPanel();

    expect(await screen.findByText("<script>Choose migration</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    await waitFor(() => expect(decideTransformationPrompt).toHaveBeenCalledWith("run-1", "prompt-1", expect.objectContaining({
      expected_state_version: 3,
      prompt_checksum: "sha256:prompt",
      selected_option_id: "yes",
    })));
    expect(refreshAuthoritativeState).toHaveBeenCalled();
  });

  it("projects G08 version proof and changed-file evidence links", async () => {
    vi.mocked(getTransformation).mockResolvedValue({ ...projection, status: "waiting_gate", active_gate: "G08" });
    renderPanel({
      workflowEvents: [event("VERSION_VERIFICATION_PASSED", 1), event("STAGE_TRANSFORMATION_COMPLETED", 2), event("G08_CREATED", 3)],
      artifacts: [
        { artifact_id: "version", run_id: "run-1", stage_id: "stage-1", artifact_type: "json", relative_path: "04_workflow_state/stages/stage-1/transformation/version-verification.json", created_at: "now", checksum: "sha256:version" },
        { artifact_id: "ledger", run_id: "run-1", stage_id: "stage-1", artifact_type: "json", relative_path: "04_workflow_state/stages/stage-1/transformation/migration-ledger.json", created_at: "now", checksum: "sha256:ledger" },
      ],
    });

    expect(await screen.findByText("Passed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /migration-ledger\.json/ })).toBeInTheDocument();
    expect(screen.getAllByText("Validation review").length).toBeGreaterThan(0);
  });

  it("projects validation failure, classification, repair review, and G10 state", async () => {
    vi.mocked(requestRepairRevision).mockResolvedValue({ attempt_id: "repair-2", status: "evidence_frozen", idempotent_replay: false });
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "waiting_gate",
      active_gate: "G10",
      repair_attempt_id: "repair-1",
      repair_status: "reviewed",
      repair_risk_level: "medium",
      repair_proposal_checksum: "sha256:proposal",
      repair_review_checksum: "sha256:review",
      repair_proposal_id: "proposal-1",
      repair_base_checksum: `sha256:${"1".repeat(64)}`,
      repair_safe_diff: "--- a/app.ts\n+++ b/app.ts\n@@ -1 +1 @@\n-old\n+new\n",
      repair_review: {
        decision: "accept",
        findings: ["Scoped change"],
        policy_checks: ["paths"],
        risk_assessment: "Medium risk",
        required_validation_targets: ["build"],
        limitations: ["Manual smoke check"],
      },
      repair_rationale: ["Fix the failed transform"],
    });
    renderPanel({ workflowEvents: [
      event("STAGE_VALIDATION_FAILED", 1),
      event("FAILURE_EVIDENCE_FROZEN", 2),
      event("FAILURE_CLASSIFIED", 3),
      event("REPAIR_REVIEW_COMPLETED", 4),
      event("G10_CREATED", 5),
    ] });

    expect(await screen.findByText("Waiting for Repair approval")).toBeInTheDocument();
    expect(screen.getByText("Proposal evidence")).toBeInTheDocument();
    expect(screen.getByText("Verdict")).toBeInTheDocument();
    expect(screen.getAllByText("Repair approval").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Unified diff viewer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request changes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Exact revision instruction"), {
      target: { value: "Keep the accepted shape but handle empty values" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Request changes" }));
    await waitFor(() => expect(requestRepairRevision).toHaveBeenCalledWith(
      "run-1",
      "repair-1",
      expect.objectContaining({ instruction: "Keep the accepted shape but handle empty values" }),
    ));
  });

  it("submits an exact human instruction for a reviewer-requested revision", async () => {
    const baseChecksum = `sha256:${"2".repeat(64)}`;
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "waiting_repair_revision",
      current_node: "review_repair",
      active_gate: null,
      active_gate_package_checksum: null,
      repair_attempt_id: "repair-1",
      repair_attempt_number: 1,
      repair_status: "request_changes",
      repair_proposal_id: "proposal-1",
      repair_base_checksum: baseChecksum,
      repair_review: {
        decision: "request_changes",
        findings: ["Handle the null response"],
        policy_checks: ["paths"],
        risk_assessment: "Low risk",
        required_validation_targets: ["build"],
        limitations: [],
      },
    });
    vi.mocked(requestRepairRevision).mockResolvedValue({ attempt_id: "repair-2", status: "evidence_frozen", idempotent_replay: false });
    renderPanel();

    expect(await screen.findByRole("heading", { name: "Repair revision required" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Exact revision instruction"), {
      target: { value: "Handle the null response before rendering" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Request changes" }));

    await waitFor(() => expect(requestRepairRevision).toHaveBeenCalledWith(
      "run-1",
      "repair-1",
      expect.objectContaining({
        attempt_id: "repair-1",
        proposal_id: "proposal-1",
        base_checksum: baseChecksum,
        instruction: "Handle the null response before rendering",
      }),
    ));
    expect(screen.getByRole("button", { name: "Reject repair" })).toBeInTheDocument();
    expect(rejectRepair).not.toHaveBeenCalled();
  });

  it("submits a repair revision once, shows the returned child attempt id, and clears the instruction", async () => {
    const baseChecksum = `sha256:${"4".repeat(64)}`;
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "waiting_repair_revision",
      current_node: "review_repair",
      active_gate: null,
      active_gate_package_checksum: null,
      repair_attempt_id: "repair-1",
      repair_attempt_number: 1,
      repair_status: "request_changes",
      repair_proposal_id: "proposal-1",
      repair_base_checksum: baseChecksum,
      repair_review: {
        decision: "request_changes",
        findings: ["Handle the null response"],
        policy_checks: ["paths"],
        risk_assessment: "Low risk",
        required_validation_targets: ["build"],
        limitations: [],
      },
    });
    let resolveRevision!: (value: { attempt_id: string; status: string; idempotent_replay: boolean }) => void;
    vi.mocked(requestRepairRevision).mockImplementation(() => new Promise((resolve) => { resolveRevision = resolve; }));
    renderPanel();

    fireEvent.change(await screen.findByLabelText("Exact revision instruction"), {
      target: { value: "Update package.json to align with Angular 19" },
    });
    const button = screen.getByRole("button", { name: "Request changes" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(requestRepairRevision).toHaveBeenCalledTimes(1);

    resolveRevision({ attempt_id: "repair-2", status: "evidence_frozen", idempotent_replay: false });
    expect(await screen.findByText(/child attempt repair-2/)).toBeInTheDocument();
    expect(screen.getByText(/status: evidence_frozen/)).toBeInTheDocument();
    expect(screen.getByLabelText("Exact revision instruction")).toHaveValue("");
  });

  it("shows the backend error code and message and preserves the instruction after a failed revision", async () => {
    const baseChecksum = `sha256:${"5".repeat(64)}`;
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "waiting_repair_revision",
      current_node: "review_repair",
      active_gate: null,
      active_gate_package_checksum: null,
      repair_attempt_id: "repair-1",
      repair_attempt_number: 1,
      repair_status: "request_changes",
      repair_proposal_id: "proposal-1",
      repair_base_checksum: baseChecksum,
      repair_review: {
        decision: "request_changes",
        findings: ["Handle the null response"],
        policy_checks: ["paths"],
        risk_assessment: "Low risk",
        required_validation_targets: ["build"],
        limitations: [],
      },
    });
    vi.mocked(requestRepairRevision).mockRejectedValue(new ApiClientError(
      "rejected",
      422,
      "POST",
      "/revisions",
      JSON.stringify({
        error_code: "validation_error",
        message: "Request validation failed.",
        correlation_id: "corr-1",
        details: {},
      }),
    ));
    renderPanel();

    fireEvent.change(await screen.findByLabelText("Exact revision instruction"), {
      target: { value: "Keep package.json but fix the lockfile alignment" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Request changes" }));

    expect(await screen.findByText("Request validation failed.")).toBeInTheDocument();
    expect(screen.getByText("Error code: validation_error")).toBeInTheDocument();
    expect(screen.getByLabelText("Exact revision instruction")).toHaveValue("Keep package.json but fix the lockfile alignment");
    expect(getTransformation).toHaveBeenCalledTimes(1);
  });

  it("projects sealed route continuation and full completion", async () => {
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "completed",
      current_node: "terminal",
      stage_status: "sealed",
      active_gate: null,
      active_gate_package_checksum: null,
      sealed_chain_hash: "sha256:seal",
      route_stages: [
        { stage_id: "stage-1", source_version: "18.x", target_version: "19.x", status: "sealed" },
        { stage_id: "stage-2", source_version: "19.x", target_version: "21.x", status: "sealed" },
      ],
    });
    renderPanel({ workflowEvents: [event("G12_APPROVED", 1), event("STAGE_SEALED", 2), event("NEXT_STAGE_MATERIALIZED", 3), event("STAGED_MIGRATION_COMPLETED", 4)] });

    expect((await screen.findAllByText(/Sealed manifest checksum: sha256:seal/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Angular 19\.x to 21\.x/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Cancel Transformer" })).not.toBeInTheDocument();
  });

  it("shows a stale 409 clearly and reloads both authoritative projections", async () => {
    vi.mocked(getTransformation).mockResolvedValue(projection);
    vi.mocked(decideTransformationGate).mockRejectedValue(new ApiClientError(
      "conflict",
      409,
      "POST",
      "/transformation",
      JSON.stringify({ error: { code: "TRANSFORMATION_STATE_CONFLICT" } }),
    ));
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("TRANSFORMATION_STATE_CONFLICT");
    expect(screen.getByRole("alert")).toHaveTextContent("reloaded");
    expect(refreshAuthoritativeState).toHaveBeenCalled();
    expect(getTransformation).toHaveBeenCalledTimes(2);
  });

  it("projects exact expected and actual runtime-profile stale evidence", async () => {
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "blocked",
      current_node: "resolve_runtime",
      last_error_code: "EXECUTION_PROFILE_STALE",
      last_error_message: "Selected execution profile no longer matches the approved stage plan",
      runtime_profile_binding: {
        expected: {
          statuses: ["resolved", "selected"],
          profile_id: "profile-1",
          checksums: ["sha256:expected"],
        },
        actual: {
          status: "resolved",
          profile_id: "profile-1",
          checksum: "sha256:actual",
          persisted_profile_checksum: "sha256:actual",
        },
        mismatches: ["checksum"],
      },
    });
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent("EXECUTION_PROFILE_STALE");
    expect(screen.getByRole("alert")).toHaveTextContent("sha256:expected");
    expect(screen.getByRole("alert")).toHaveTextContent("sha256:actual");
  });

  it("keeps failed executions and their successful retries visible", async () => {
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      stage_id: "stage-2",
      source_version: "19.x",
      target_version: "20.x",
      route_stages: [
        { stage_id: "stage-1", source_version: "18.x", target_version: "19.x", status: "sealed" },
        { stage_id: "stage-2", source_version: "19.x", target_version: "20.x", status: "sealed" },
      ],
      stage_status: "sealed",
      status: "completed",
      active_gate: null,
    });
    vi.mocked(listCommandExecutions).mockResolvedValue({
      run_id: "run-1",
      total: 2,
      executions: [
        { execution_id: "exec-failed", run_id: "run-1", command_id: "angular-update", status: "failed", state_version: 1, event_sequence: 1, idempotent_replay: false, stage_id: "stage-2", authorization_id: null, template_id: null, template_version: null, plan_id: null, plan_version: null, execution_profile_id: null, workspace_alias: null, created_at: "2026-07-30T10:00:00Z", started_at: "2026-07-30T10:00:00Z", completed_at: "2026-07-30T10:01:00Z", duration_ms: 60000, exit_code: 1, failure_code: "peer_conflict", correlation_id: null, artifact_ids: [], request_payload_hash: null, failure_reason: "Angular peer dependency conflict" },
        { execution_id: "exec-retry", run_id: "run-1", command_id: "angular-update", status: "succeeded", state_version: 2, event_sequence: 2, idempotent_replay: false, stage_id: "stage-2", authorization_id: null, template_id: null, template_version: null, plan_id: null, plan_version: null, execution_profile_id: null, workspace_alias: null, created_at: "2026-07-30T10:02:00Z", started_at: "2026-07-30T10:02:00Z", completed_at: "2026-07-30T10:03:00Z", duration_ms: 60000, exit_code: 0, failure_code: null, correlation_id: null, artifact_ids: [], request_payload_hash: null },
      ],
    });
    renderPanel({ workflowEvents: [event("COMMAND_QUEUED", 1, { execution_id: "exec-retry", parent_execution_id: "exec-failed" })] });

    expect(await screen.findByText(/Angular peer dependency conflict/)).toBeInTheDocument();
    expect(screen.getAllByText("angular-update").length).toBe(2);
    expect(screen.getByText(/Retry parent: exec-failed/)).toBeInTheDocument();
    expect(screen.getByText(/Execution ID: exec-failed/)).toBeInTheDocument();
    expect(screen.getByText(/Execution ID: exec-retry/)).toBeInTheDocument();
  });

  it("renders the prepared next stage and its sealed source lineage", async () => {
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      stage_id: "stage-3",
      source_version: "20.x",
      target_version: "21.x",
      stage_status: "prepared",
      status: "waiting_gate",
      active_gate: "G07",
      route_stages: [
        { stage_id: "stage-1", source_version: "18.x", target_version: "19.x", status: "sealed" },
        { stage_id: "stage-2", source_version: "19.x", target_version: "20.x", status: "sealed" },
        { stage_id: "stage-3", source_version: "20.x", target_version: "21.x", status: "prepared" },
      ],
    });
    renderPanel();

    expect(await screen.findByRole("heading", { name: "Stage-start approval" })).toBeInTheDocument();
    expect(screen.getAllByText(/Angular 20\.x to 21\.x/).length).toBeGreaterThan(0);
    expect(screen.getByText("Angular 19.x to 20.x sealed output")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(decideTransformationGate).not.toHaveBeenCalled();
  });

  it("fails closed when the backend decision evidence is missing or unsupported", async () => {
    vi.mocked(getTransformation).mockResolvedValue({ ...projection, active_gate: "UNKNOWN", active_gate_package_checksum: null });
    renderPanel();

    expect(await screen.findByText("This decision type is unsupported by the frontend.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });
});
