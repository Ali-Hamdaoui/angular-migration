import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { getPlan, createPlan } from "@/api/plans";
import { MigrationPlanPanel } from "@/components/MigrationPlanPanel";
import type { ArtifactRefDto, AuthoritativeRunStateDto } from "@/types/generated/api";
import type { PlanResponse } from "@/types/planning";

vi.mock("@/api/plans", () => ({ getPlan: vi.fn(), createPlan: vi.fn() }));

const checksum = (letter: string) => `sha256:${letter.repeat(64)}`;
const artifact: ArtifactRefDto = { artifact_id: "fact-1", run_id: "run-1", stage_id: null, artifact_type: "json", relative_path: "02_analysis/findings.json", created_at: "now", checksum: checksum("a") };
const response: PlanResponse = {
  run_id: "run-1", status: "generated", plan: { plan_id: "plan-1", run_id: "run-1", version: 1, source_family: "angular-18.x", source_exact: "18.2.13", target_family: "angular-21.x", route: ["stage-18-to-19", "stage-19-to-20", "stage-20-to-21"], mode: "strict_compatibility", catalogue_version: "catalog-v1", stage_plan_strategy: "resolve_exact_before_each_stage", approval_policy: "mandatory-human-v1", repair_policy: { policy_id: "repair-v1", enabled: true, proposer_reviewer_required: true, human_apply_required: true }, command_policy: "structured-registry-v1", artifact_policy: "immutable-stage-scoped-v1", checksum: checksum("b") },
  stage_plan: { stage_plan_id: "stage-plan-1", stage_id: "stage-18-to-19", plan_version: 1, input_fingerprint: checksum("c"), source_family: "angular-18.x", source_exact: "18.2.13", target_family: "angular-19.x", target_exact: "19.2.0", execution_profile_id: "profile-1", commands: { bootstrap_install: [{ command_id: "npm-ci", executable: "npm", arguments: ["ci"], shell: false, working_directory_alias: "stage_workspace", timeout_seconds: 300, network_profile: "approved-registries-only", conditional: false }] }, build_system_decision: { decision_id: "decision-1", builder: "@angular-devkit/build-angular:application", action: "preserve", rationale: "Keep builder", checksum: checksum("d") }, validation_policy: { policy_id: "validation-v1", baseline_comparison_required: true, route_comparison_required: true, backend_comparison_required: true, required_checks: ["build", "test"] }, recovery_policy: { policy_id: "recovery-v1", safe_boundaries: ["before-install"], rerun_read_only_steps: true, reconstruct_mutating_steps: true }, repair_policy: { policy_id: "repair-v1", enabled: true, proposer_reviewer_required: true, human_apply_required: true }, forbidden_change_policy: { policy_id: "forbidden-v1", actions: ["optional_signals_migration"] }, checksum: checksum("e") }, plan_checksum: checksum("b"), stage_plan_checksum: checksum("e"), artifact_ids: ["plan-artifact"], artifact_checksums: { "plan-artifact": checksum("f") }, artifact_links: { "plan-artifact": "/api/v1/artifacts/plan-artifact" }, builder_decision: {}, state_version: 3, event_sequence: 2, idempotent_replay: false,
};
const state = { run_id: "run-1", state_version: 1, artifacts: [artifact], plan_inputs: { source_exact: "18.2.13", source_family: "angular-18.x", target_family: "angular-21.x", target_cli_exact: "21.0.0", catalogue_version: "catalog-v1", input_fingerprint: checksum("c"), execution_profile_id: "profile-1", stage_route: [["angular-18.x", "angular-19.x", "stage-18-to-19", "19.2.0"]], builder: "@angular-devkit/build-angular:application" } } as unknown as AuthoritativeRunStateDto;
const props = { runId: "run-1", initialState: state, connectionStatus: "open", artifacts: [artifact], workflowEvents: [{ event_type: "G05_APPROVED", sequence: 1 }], refreshAuthoritativeState: vi.fn().mockResolvedValue(undefined) };

describe("MigrationPlanPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders route, Stage 1 commands, policies, and artifact checksums", async () => {
    vi.mocked(getPlan).mockResolvedValue(response);
    render(<MigrationPlanPanel {...props} />);
    expect(await screen.findByText("Major-stage route")).toBeInTheDocument();
    expect(screen.getByText("stage-18-to-19")).toBeInTheDocument();
    expect(screen.getByText(/npm-ci/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Builder" }));
    expect(screen.getByText("Build-system decision")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Artifacts" }));
    expect(screen.getByRole("link", { name: "plan-artifact" })).toHaveAttribute("href", "/api/v1/artifacts/plan-artifact");
  });

  it("renders empty prerequisites and handles stale generation", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("missing", 404));
    render(<MigrationPlanPanel {...props} initialState={{ ...state, plan_inputs: undefined } as unknown as AuthoritativeRunStateDto} />);
    expect(await screen.findByText("No MigrationPlan is available yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate MigrationPlan" })).toBeDisabled();
  });

  it("reloads authoritative state after a stale generation", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("missing", 404));
    vi.mocked(createPlan).mockRejectedValue(new ApiClientError("stale", 409));
    render(<MigrationPlanPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Generate MigrationPlan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("stale state version");
    expect(props.refreshAuthoritativeState).toHaveBeenCalled();
  });

  it("renders backend failure with correlation guidance", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("failed", 503, "GET", "/plan", JSON.stringify({ correlation_id: "corr-plan" })));
    render(<MigrationPlanPanel {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("corr-plan");
  });
});
