import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { getPlan } from "@/api/plans";
import { MigrationPlanPanel } from "@/components/MigrationPlanPanel";
import type { ArtifactRefDto } from "@/types/generated/api";
import type { PlanResponse } from "@/types/planning";
import { feasibilityPrerequisites, makeArtifact, makeAuthoritativeRun, makeEvent } from "@/test/authoritativeFixtures";

vi.mock("@/api/plans", () => ({ getPlan: vi.fn(), createPlan: vi.fn() }));

const checksum = (letter: string) => `sha256:${letter.repeat(64)}`;
const artifact: ArtifactRefDto = makeArtifact({ artifact_id: "fact-1", run_id: "run-1", relative_path: "02_analysis/findings.json", checksum: checksum("a") });
const response: PlanResponse = {
  run_id: "run-1", status: "generated", plan: { plan_id: "plan-1", run_id: "run-1", version: 1, source_family: "angular-18.x", source_exact: "18.2.13", target_family: "angular-21.x", route: ["stage-18-to-19", "stage-19-to-20", "stage-20-to-21"], mode: "strict_compatibility", catalogue_version: "catalog-v1", stage_plan_strategy: "resolve_exact_before_each_stage", approval_policy: "mandatory-human-v1", repair_policy: { policy_id: "repair-v1", enabled: true, proposer_reviewer_required: true, human_apply_required: true }, command_policy: "structured-registry-v1", artifact_policy: "immutable-stage-scoped-v1", checksum: checksum("b") },
  stage_plan: { stage_plan_id: "stage-plan-1", stage_id: "stage-18-to-19", plan_version: 1, input_fingerprint: checksum("c"), source_family: "angular-18.x", source_exact: "18.2.13", target_family: "angular-19.x", target_exact: "19.2.0", execution_profile_id: "profile-1", commands: { bootstrap_install: [{ command_id: "npm-ci", executable: "npm", arguments: ["ci"], shell: false, working_directory_alias: "stage_workspace", timeout_seconds: 300, network_profile: "approved-registries-only", conditional: false }] }, build_system_decision: { decision_id: "decision-1", builder: "@angular-devkit/build-angular:application", action: "preserve", rationale: "Keep builder", checksum: checksum("d") }, validation_policy: { policy_id: "validation-v1", baseline_comparison_required: true, route_comparison_required: true, backend_comparison_required: true, required_checks: ["build", "test"] }, recovery_policy: { policy_id: "recovery-v1", safe_boundaries: ["before-install"], rerun_read_only_steps: true, reconstruct_mutating_steps: true }, repair_policy: { policy_id: "repair-v1", enabled: true, proposer_reviewer_required: true, human_apply_required: true }, forbidden_change_policy: { policy_id: "forbidden-v1", actions: ["optional_signals_migration"] }, checksum: checksum("e") }, plan_checksum: checksum("b"), stage_plan_checksum: checksum("e"), artifact_ids: ["plan-artifact"], artifact_checksums: { "plan-artifact": checksum("f") }, artifact_links: { "plan-artifact": "/api/v1/artifacts/plan-artifact" }, builder_decision: {}, state_version: 3, event_sequence: 2, idempotent_replay: false,
};
const state = makeAuthoritativeRun({ run_id: "run-1", state_version: 1, artifacts: [artifact] });
const planningPrerequisites = [...feasibilityPrerequisites, makeEvent("G05_APPROVED", 6), makeEvent("MIGRATION_PLAN_CREATED", 7), makeEvent("STAGE_PLAN_CREATED", 8), makeEvent("G06_CREATED", 9)];
const props = { runId: "run-1", initialState: state, connectionStatus: "open", artifacts: [artifact], workflowEvents: planningPrerequisites, refreshAuthoritativeState: vi.fn().mockResolvedValue(undefined) };

describe("MigrationPlanPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a subordinate heading when embedded in a pipeline stage", () => {
    render(<MigrationPlanPanel {...props} headingLevel={4} />);
    expect(screen.getByRole("heading", { name: "Migration plan", level: 4 })).toBeInTheDocument();
  });

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

  it("renders multiple commands sharing a command_id without duplicate React keys", async () => {
    const command = (arg: string) => ({
      command_id: "npm-pkg-set",
      executable: "npm",
      arguments: ["pkg", "set", arg],
      shell: false as const,
      working_directory_alias: "stage_workspace",
      timeout_seconds: 120,
      network_profile: "approved-registries-only",
      conditional: false,
    });
    const dupResponse: PlanResponse = {
      ...response,
      stage_plan: {
        ...response.stage_plan,
        commands: {
          package_sets: [command("@angular/core"), command("@angular/common"), command("@angular/cli")],
          bootstraps: [command("@angular/platform-browser")],
        },
      },
    };
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(getPlan).mockResolvedValue(dupResponse);
    render(<MigrationPlanPanel {...props} />);
    expect(await screen.findByText("Major-stage route")).toBeInTheDocument();

    expect(screen.getByText(/"@angular\/core"/)).toBeInTheDocument();
    expect(screen.getByText(/"@angular\/common"/)).toBeInTheDocument();
    expect(screen.getByText(/"@angular\/cli"/)).toBeInTheDocument();
    expect(screen.getByText(/"@angular\/platform-browser"/)).toBeInTheDocument();
    expect(errorSpy).not.toHaveBeenCalledWith(expect.stringContaining("same key"));

    errorSpy.mockRestore();
  });

  it("preserves the Builder tab after a same-checksum authoritative refresh", async () => {
    let resolveRefresh!: (value: PlanResponse) => void;
    vi.mocked(getPlan).mockResolvedValue(response);
    const { rerender } = render(<MigrationPlanPanel {...props} />);
    expect(await screen.findByText("Major-stage route")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Builder" }));
    expect(screen.getByRole("tab", { name: "Builder" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Build-system decision");

    vi.mocked(getPlan).mockImplementation(() => new Promise<PlanResponse>((resolve) => { resolveRefresh = resolve; }));
    rerender(<MigrationPlanPanel {...props} initialState={{ ...state, state_version: state.state_version + 1 }} />);
    expect(await screen.findByText("Loading authoritative MigrationPlan...")).toBeInTheDocument();
    resolveRefresh(response);
    await waitFor(() => expect(screen.queryByText("Loading authoritative MigrationPlan...")).not.toBeInTheDocument());

    expect(screen.getByRole("tab", { name: "Builder" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Build-system decision");
  });

  it("renders an empty backend-owned plan without enabling a local generation action", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("missing", 404));
    render(<MigrationPlanPanel {...props} />);
    expect(await screen.findByText("No persisted migration plan is available yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate MigrationPlan" })).not.toBeInTheDocument();
  });

  it("fails closed when the backend reports blocked plan evidence", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("blocked", 409));
    render(<MigrationPlanPanel {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Plan evidence is blocked or failed integrity validation");
  });

  it("renders backend failure with correlation guidance", async () => {
    vi.mocked(getPlan).mockRejectedValue(new ApiClientError("failed", 503, "GET", "/plan", JSON.stringify({ correlation_id: "corr-plan" })));
    render(<MigrationPlanPanel {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("corr-plan");
  });
});
