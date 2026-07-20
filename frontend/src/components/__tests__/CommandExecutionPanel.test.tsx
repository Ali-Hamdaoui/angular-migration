import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandExecutionPanel } from "@/components/CommandExecutionPanel";
import { executeApprovedCommand, getCommandExecution, listCommandExecutions } from "@/api/commands";

vi.mock("@/api/commands", () => ({ executeApprovedCommand: vi.fn(), getCommandExecution: vi.fn(), listCommandExecutions: vi.fn() }));

const authorization = { authorization_id: "auth-1", run_id: "run-1", stage_id: "stage-1", plan_id: "plan-1", command_id: "npm-ci", executable: "npm", arguments: ["ci"], cwd_alias: "BASELINE_SANDBOX", execution_profile_id: "profile-1", decision: "accepted", reasons: [], policy_version: "v1", idempotent_replay: false, expected_state_version: 7, authoritative_state_version: 7, artifact_id: null, correlation_id: "corr-1", request_payload_hash: "sha256:req", decision_timestamp: "2026-07-20T10:00:00Z" } as never;
const base = { execution_id: "exec-1", run_id: "run-1", command_id: "npm-ci", status: "queued", state_version: 8, event_sequence: 4, idempotent_replay: false, stage_id: "stage-1", authorization_id: "auth-1", template_id: "tpl-1", template_version: 1, plan_id: "plan-1", plan_version: 7, execution_profile_id: "profile-1", workspace_alias: "BASELINE_SANDBOX", created_at: "2026-07-20T10:00:00Z", started_at: null, completed_at: null, duration_ms: null, exit_code: null, failure_code: null, correlation_id: "corr-1", artifact_ids: ["manifest-1", "stdout-1"], request_payload_hash: "sha256:req" };

describe("CommandExecutionPanel", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(listCommandExecutions).mockResolvedValue({ run_id: "run-1", executions: [], total: 0 }); vi.stubGlobal("confirm", vi.fn(() => true)); });

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
    expect(screen.getByRole("link", { name: /Open artifact manifest-1/ })).toHaveAttribute("href", "/api/v1/artifacts/manifest-1");
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
});
