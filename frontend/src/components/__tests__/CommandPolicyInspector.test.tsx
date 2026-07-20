import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandPolicyInspector } from "@/components/CommandPolicyInspector";
import { listCommandTemplates, validateCommandPolicy } from "@/api/commands";
import { getStagePlan } from "@/api/plans";
import { ApiClientError } from "@/api/client";

vi.mock("@/api/commands", () => ({ listCommandTemplates: vi.fn(), validateCommandPolicy: vi.fn() }));
vi.mock("@/api/plans", () => ({ getStagePlan: vi.fn() }));

const templates = {
  total: 2,
  templates: [
    { template_id: "tpl-npm", command_id: "npm-ci", executable: "npm", arguments: ["ci"], executable_aliases: [], description: "Install", status: "active", version: 3, allowed_env_vars: [], max_output_bytes: 1000, created_at: null, updated_at: null },
    { template_id: "tpl-check", command_id: "ng-version", executable: "npx", arguments: ["ng", "version"], executable_aliases: [], description: "Check", status: "active", version: 1, allowed_env_vars: [], max_output_bytes: 1000, created_at: null, updated_at: null },
  ],
};
const plan = {
  run_id: "run-1", status: "approved", plan: { plan_id: "plan-1", run_id: "run-1", version: 7, source_family: "angular-18.x", source_exact: "18.2.0", target_family: "angular-19.x", route: ["stage-1"], mode: "staged", catalogue_version: "catalog-1", stage_plan_strategy: "exact", approval_policy: "human", repair_policy: {}, command_policy: "registered", artifact_policy: "immutable", checksum: "sha256:plan" },
  stage_plan: { stage_plan_id: "stage-plan-1", stage_id: "stage-1", plan_version: 7, input_fingerprint: "sha256:input", source_family: "angular-18.x", source_exact: "18.2.0", target_family: "angular-19.x", target_exact: "19.2.0", execution_profile_id: "profile-approved", commands: { install: [{ command_id: "npm-ci", executable: "npm", arguments: ["ci"], shell: false, working_directory_alias: "BASELINE_SANDBOX", timeout_seconds: 300, network_profile: "approved-registries-only", conditional: false }], check: [{ command_id: "ng-version", executable: "npx", arguments: ["ng", "version"], shell: false, working_directory_alias: "BASELINE_SANDBOX", timeout_seconds: 60, network_profile: "none", conditional: false }] }, build_system_decision: {}, validation_policy: {}, recovery_policy: {}, repair_policy: {}, forbidden_change_policy: {}, checksum: "sha256:stage" }, plan_checksum: "sha256:plan", stage_plan_checksum: "sha256:stage", artifact_ids: ["auth-plan"], artifact_checksums: { "auth-plan": "sha256:evidence" }, artifact_links: { "auth-plan": "/api/v1/artifacts/auth-plan" }, builder_decision: {}, state_version: 7, event_sequence: 3, idempotent_replay: false,
} as never;
const state = { run_id: "run-1", state_version: 7, workspace_aliases: { BASELINE_SANDBOX: "C:/safe/run/baseline-sandbox" }, workflow_events: [{ event_id: "stage", run_id: "run-1", stage_id: "stage-1", event_type: "STAGE_PLAN_CREATED", occurred_at: "2026-07-20T10:00:00Z", sequence: 1, payload: {} }], artifacts: [] } as never;

describe("CommandPolicyInspector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listCommandTemplates).mockResolvedValue(templates);
    vi.mocked(getStagePlan).mockResolvedValue(plan);
  });

  it("constructs an authoritative safe request and reuses its key on retry", async () => {
    vi.mocked(validateCommandPolicy).mockResolvedValue({ authorization_id: "auth-1", run_id: "run-1", stage_id: "stage-1", plan_id: "plan-1", command_id: "npm-ci", executable: "npm", arguments: ["ci"], cwd_alias: "BASELINE_SANDBOX", execution_profile_id: "profile-approved", decision: "accepted", reasons: [], policy_version: "s3-f01-v1", idempotent_replay: false, expected_state_version: 7, authoritative_state_version: 7, artifact_id: "evidence-1", correlation_id: "corr-1", request_payload_hash: "sha256:req", decision_timestamp: "2026-07-20T10:00:01Z" });
    render(<CommandPolicyInspector runId="run-1" runState={state} />);
    await screen.findByText("npm-ci v3");
    fireEvent.click(screen.getAllByRole("button", { name: "Validate against policy" })[0]);
    await screen.findByText("ACCEPTED");
    const first = vi.mocked(validateCommandPolicy).mock.calls[0][0];
    expect(first).toMatchObject({ run_id: "run-1", stage_id: "stage-1", plan_id: "plan-1", plan_version: 7, working_directory_alias: "BASELINE_SANDBOX", working_directory: "C:/safe/run/baseline-sandbox", execution_profile_id: "profile-approved", expected_state_version: 7, shell: false });
    expect(first.arguments).toEqual(["ci"]);
    expect(first.executable).toBe("npm");
    expect(first.idempotency_key).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Validate against policy" })[0]);
    expect(vi.mocked(validateCommandPolicy).mock.calls[1][0].idempotency_key).not.toBe(first.idempotency_key);
  });

  it("renders rejection code, correlation, and evidence guidance", async () => {
    vi.mocked(validateCommandPolicy).mockResolvedValue({ ...plan, authorization_id: "auth-2", run_id: "run-1", stage_id: "stage-1", plan_id: "plan-1", command_id: "npm-ci", executable: "npm", arguments: ["ci"], cwd_alias: "BASELINE_SANDBOX", execution_profile_id: "profile-approved", decision: "rejected", reasons: ["COMMAND_NOT_IN_APPROVED_PLAN: command is not approved"], policy_version: "s3-f01-v1", idempotent_replay: false, expected_state_version: 7, authoritative_state_version: 7, artifact_id: "reject-evidence", correlation_id: "corr-reject", request_payload_hash: null, decision_timestamp: null } as never);
    render(<CommandPolicyInspector runId="run-1" runState={state} />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Validate against policy" }))[0]);
    expect(await screen.findByText("COMMAND_NOT_IN_APPROVED_PLAN")).toBeInTheDocument();
    expect(screen.getByText(/corr-reject/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open authorization evidence/ })).toHaveAttribute("href", "/api/v1/artifacts/reject-evidence");
  });

  it("does not resubmit stale state and refreshes the authoritative run", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    vi.mocked(validateCommandPolicy).mockRejectedValueOnce(new ApiClientError("stale", 409, "POST", "/policy", JSON.stringify({ error_code: "STALE_STATE_VERSION", message: "The run state is stale", correlation_id: "corr-stale" })));
    render(<CommandPolicyInspector runId="run-1" runState={state} refreshAuthoritativeState={refresh} />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Validate against policy" }))[0]);
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/run changed while this page was open/i)).toBeInTheDocument();
    expect(vi.mocked(validateCommandPolicy)).toHaveBeenCalledTimes(1);
  });
});
