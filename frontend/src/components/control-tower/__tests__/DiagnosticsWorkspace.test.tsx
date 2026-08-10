import { fireEvent, render, screen, within } from "@testing-library/react";
import type { AuthoritativeRunStateDto, CommandExecutionResponseDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";
import { DiagnosticsWorkspace } from "../DiagnosticsWorkspace";

const event = (event_type: string, sequence: number, payload: Record<string, unknown> = {}) => ({
  event_id: `event-${sequence}`,
  run_id: "run-1",
  stage_id: "stage-20-21",
  event_type,
  occurred_at: `2026-08-10T10:0${sequence}:00Z`,
  sequence,
  payload,
});

const run = (workflow_events: AuthoritativeRunStateDto["workflow_events"]): AuthoritativeRunStateDto => ({
  run_id: "run-1",
  status: "RUNNING",
  run_phase: "STAGED_MIGRATION",
  phase_status: "running",
  approval_status: "pending",
  repair_status: "not_required",
  state_version: 4,
  preflight_id: "preflight-1",
  source_path: "C:/source",
  target_output_path: "C:/target",
  graph_thread_id: "thread-1",
  created_at: "2026-08-10T10:00:00Z",
  updated_at: "2026-08-10T10:00:00Z",
  artifacts: [],
  workflow_events,
});

const projection = (overrides: Partial<TransformationProjection> = {}): TransformationProjection => ({
  run_id: "run-1", continuation_id: "cont-1", stage_id: "stage-20-21", status: "blocked", current_node: "version_verify", state_version: 5,
  stage_status: "blocked", source_version: "20.2.0", target_version: "21.0.0", checkpoint_kind: null, workspace_fingerprint: null,
  active_gate: null, active_gate_package_checksum: null, active_command_id: null, active_command_status: null, active_prompt_id: null,
  active_prompt_checksum: null, active_prompt_text: null, active_prompt_options: [], active_prompt_explanation: null, repair_attempt_id: null,
  repair_attempt_number: null, repair_status: null, repair_risk_level: null, repair_proposal_checksum: null, repair_review_checksum: null,
  repair_proposal_id: null, repair_base_checksum: null, repair_safe_diff: null, repair_review: null, repair_rationale: [], repair_apply_checksum: null,
  repair_validation_checksum: null, workflow_step: "version_verify", active_command_phase: null, stage_start_fingerprint: null,
  repair_contract: null, dependency_operation: null, completed_transition_phases: [], repair_verification: null, dependency_closure: null,
  validation_results: {}, active_error: { code: "NG_VERSION_MISMATCH", message: "Angular CLI did not reach the requested target." },
  historical_diagnostics: [], route_stages: [], sealed_chain_hash: null, last_error_code: "NG_VERSION_MISMATCH", last_error_message: "Angular CLI did not reach the requested target.",
  runtime_profile_binding: null, cancel_requested_at: null, ...overrides,
});

const execution = (overrides: Partial<CommandExecutionResponseDto> = {}): CommandExecutionResponseDto => ({
  execution_id: "exec-1", run_id: "run-1", command_id: "ng-version", status: "failed", state_version: 5, event_sequence: 6,
  idempotent_replay: false, stage_id: "stage-20-21", authorization_id: null, template_id: "template-1", template_version: 1,
  plan_id: null, plan_version: null, execution_profile_id: null, workspace_alias: "target", created_at: "2026-08-10T10:00:00Z",
  started_at: "2026-08-10T10:00:01Z", completed_at: "2026-08-10T10:00:02Z", duration_ms: 1000, exit_code: 1, failure_code: "NG_VERSION_MISMATCH",
  correlation_id: "corr-1", artifact_ids: ["artifact-log-1"], request_payload_hash: null, stdout_artifact_id: "artifact-log-1",
  stderr_artifact_id: null, command_log_artifact_id: "artifact-log-1", manifest_artifact_id: null, result_artifact_id: null,
  executable: "npx", arguments: ["ng", "version"], safe_relative_working_directory: ".", runtime_checksum: null, worker_id: null,
  failure_reason: "Angular CLI did not reach the requested target.", ...overrides,
});

function renderWorkspace(overrides: Partial<React.ComponentProps<typeof DiagnosticsWorkspace>> = {}) {
  return render(<DiagnosticsWorkspace
    run={run([
      event("RUN_CREATED", 1),
      event("TRANSFORMATION_CONTINUATION_BLOCKED", 2, { message: "Angular CLI did not reach the requested target." }),
    ])}
    runId="run-1"
    connectionStatus="open"
    connectionError={null}
    transformation={projection()}
    transformationStatus="ready"
    executions={[execution()]}
    executionStatus="ready"
    refreshTransformation={async () => undefined}
    refreshAuthoritativeState={async () => undefined}
    {...overrides}
  />);
}

describe("DiagnosticsWorkspace", () => {
  it("leads with a blocker summary and keeps raw state behind disclosure", () => {
    renderWorkspace();

    const heading = screen.getByRole("heading", { name: "Diagnostics" });
    expect(heading).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Current blocker" })).toHaveTextContent("Angular CLI did not reach the requested target");
    expect(screen.getByRole("heading", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Blocker" })).toBeInTheDocument();
    expect(screen.getByText("Raw state")).toBeInTheDocument();
    expect(screen.getByText(/"run_id": "run-1"/)).not.toBeVisible();
    fireEvent.click(screen.getByText("Raw state"));
    expect(screen.getByText(/"run_id": "run-1"/)).toBeInTheDocument();
  });

  it("humanizes workflow events while exposing raw identifiers in technical details", () => {
    renderWorkspace();
    const events = screen.getByRole("region", { name: "Authoritative workflow events" });
    expect(within(events).getByText("Transformation continuation blocked", { selector: "span" })).toBeInTheDocument();
    expect(within(events).getByText("TRANSFORMATION_CONTINUATION_BLOCKED", { selector: "code" })).not.toBeVisible();
    fireEvent.click(within(events).getAllByText("Technical details")[1]);
    expect(within(events).getAllByText("TRANSFORMATION_CONTINUATION_BLOCKED", { selector: "code" })[0]).toBeVisible();
    expect(within(events).getByText("Sequence 2")).toBeInTheDocument();
  });

  it("links command logs and provides explicit unavailable states", () => {
    renderWorkspace({ executions: [], executionStatus: "unavailable", transformation: null, transformationStatus: "empty" });
    const commands = screen.getByRole("region", { name: "Commands and logs" });
    expect(within(commands).getByText(/Not available/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "LLM activity" })).toBeInTheDocument();
  });

  it("summarizes connection recovery and disables fresh-state actions", () => {
    const refresh = vi.fn(async () => undefined);
    renderWorkspace({ connectionStatus: "recovering", refreshAuthoritativeState: refresh });
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Refreshing authoritative snapshot");
    expect(screen.getByRole("button", { name: "Refresh diagnostics" })).toBeDisabled();
  });
});
