import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandExecutionPanel } from "@/components/CommandExecutionPanel";
import { executeApprovedCommand, getCommandArtifactById, getCommandExecution, listCommandExecutions } from "@/api/commands";

vi.mock("@/api/commands", () => ({ executeApprovedCommand: vi.fn(), getCommandArtifactById: vi.fn(), getCommandExecution: vi.fn(), listCommandExecutions: vi.fn(), getCommandLogSummary: vi.fn().mockResolvedValue({ execution_id: "exec-1", run_id: "run-1", total_chunks: 0, streams: { stdout: 0, stderr: 0, system: 0 }, first_sequence: null, last_sequence: null, finalized: false, finalized_at: null, truncated: { stdout: false, stderr: false }, redaction_applied: false }) }));

const authorization = { authorization_id: "auth-1", run_id: "run-1", stage_id: "stage-1", plan_id: "plan-1", command_id: "npm-ci", executable: "npm", arguments: ["ci"], cwd_alias: "BASELINE_SANDBOX", execution_profile_id: "profile-1", decision: "accepted", reasons: [], policy_version: "v1", idempotent_replay: false, expected_state_version: 7, authoritative_state_version: 7, artifact_id: null, correlation_id: "corr-1", request_payload_hash: "sha256:req", decision_timestamp: "2026-07-20T10:00:00Z" } as never;
const base = { execution_id: "exec-1", run_id: "run-1", command_id: "npm-ci", status: "queued", state_version: 8, event_sequence: 4, idempotent_replay: false, stage_id: "stage-1", authorization_id: "auth-1", template_id: "tpl-1", template_version: 1, plan_id: "plan-1", plan_version: 7, execution_profile_id: "profile-1", workspace_alias: "BASELINE_SANDBOX", created_at: "2026-07-20T10:00:00Z", started_at: "2026-07-20T10:01:00Z", completed_at: "2026-07-20T10:02:00Z", duration_ms: 60000, exit_code: 0, failure_code: null, correlation_id: "corr-1", artifact_ids: ["manifest-1", "stdout-1"], request_payload_hash: "sha256:req", executable: "npm", arguments: ["ci", "--ignore-scripts"], safe_relative_working_directory: "stage/workspace", runtime_checksum: "sha256:runtime" };

describe("CommandExecutionPanel", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(listCommandExecutions).mockResolvedValue({ run_id: "run-1", executions: [], total: 0 }); vi.mocked(getCommandArtifactById).mockImplementation(async (artifactId) => ({ artifact: { artifact_id: artifactId, run_id: "run-1", stage_id: "stage-1", artifact_type: "command_log", relative_path: `evidence/${artifactId}.log`, created_at: "2026-07-20T10:02:00Z", checksum: "sha256:artifact" }, content: "", created_by: "worker", content_type: "text/plain", filename: `${artifactId}.log` })); vi.stubGlobal("confirm", vi.fn(() => true)); });

  it("executes an accepted authorization with a stable key and renders queued detail/evidence", async () => {
    vi.mocked(executeApprovedCommand).mockResolvedValue(base as never);
    render(<CommandExecutionPanel runId="run-1" stateVersion={7} authorization={authorization} />);
    await screen.findByText("No command executions have been recorded.");
    const executeButton = screen.getByRole("button", { name: "Execute command" });
    fireEvent.click(executeButton);
    fireEvent.click(executeButton);
    await screen.findByText("QUEUED");
    expect(vi.mocked(executeApprovedCommand)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(executeApprovedCommand)).toHaveBeenCalledWith("run-1", expect.objectContaining({ authorization_decision_id: "auth-1", expected_state_version: 7, idempotency_key: expect.any(String) }));
    expect(screen.getByRole("link", { name: /Open artifact manifest-1/ })).toHaveAttribute("href", "http://127.0.0.1:8000/api/v1/artifacts/manifest-1");
    expect(screen.getByText("npm")).toBeInTheDocument();
    expect(screen.getByText("--ignore-scripts")).toBeInTheDocument();
    expect(screen.getByText("stage/workspace")).toBeInTheDocument();
    expect(await screen.findAllByText("SHA-256: sha256:artifact")).toHaveLength(2);
    expect(await screen.findByText("command_log · evidence/manifest-1.log")).toBeInTheDocument();
  });

  it("does not enable execution for a stale authorization", async () => {
    render(<CommandExecutionPanel runId="run-1" stateVersion={8} authorization={authorization} />);
    expect(await screen.findByRole("button", { name: "Execute command" })).toBeDisabled();
    expect(screen.getByText(/authorization is stale/i)).toBeInTheDocument();
  });

  it("rehydrates an existing execution and shows final failure safely", async () => {
    vi.mocked(listCommandExecutions).mockResolvedValue({ run_id: "run-1", executions: [{ ...base, status: "failed", exit_code: 1, failure_code: "NON_ZERO_EXIT", artifact_ids: [] }] as never[], total: 1 });
    render(<CommandExecutionPanel runId="run-1" stateVersion={7} authorization={null} />);
    expect(await screen.findByText("FAILED")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "npm-ci · FAILED" }));
    expect(screen.getByText("NON_ZERO_EXIT")).toBeInTheDocument();
    expect(screen.getByText(/Evidence is not available/)).toBeInTheDocument();
    await waitFor(() => expect(getCommandExecution).not.toHaveBeenCalled());
  });

  it("reloads command state after a durable command event and exposes reconnecting recovery", async () => {
    const { rerender } = render(<CommandExecutionPanel runId="run-1" stateVersion={7} authorization={null} connectionStatus="open" workflowEvents={[]} />);
    await screen.findByText("No command executions have been recorded.");
    vi.mocked(listCommandExecutions).mockClear();
    rerender(<CommandExecutionPanel runId="run-1" stateVersion={7} authorization={null} connectionStatus="open" workflowEvents={[{ event_id: "event-command-1", run_id: "run-1", stage_id: "stage-1", event_type: "COMMAND_SUCCEEDED", occurred_at: "2026-07-20T10:02:00Z", sequence: 9, payload: {} }]} />);
    await waitFor(() => expect(listCommandExecutions).toHaveBeenCalledWith("run-1"));
    rerender(<CommandExecutionPanel runId="run-1" stateVersion={7} authorization={null} connectionStatus="recovering" workflowEvents={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent(/connection interrupted/i);
  });
});
