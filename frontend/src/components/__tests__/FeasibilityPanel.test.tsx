import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { decideG05, getFeasibility, queueFeasibilityResolution } from "@/api/compatibility";
import { FeasibilityPanel } from "@/components/FeasibilityPanel";
import type { FeasibilityResponse } from "@/types/compatibility";
import type { ArtifactRefDto, AuthoritativeRunStateDto } from "@/types/generated/api";
import { feasibilityPrerequisites, makeArtifact, makeAuthoritativeRun } from "@/test/authoritativeFixtures";

vi.mock("@/api/compatibility", () => ({ getFeasibility: vi.fn(), queueFeasibilityResolution: vi.fn(), decideG05: vi.fn() }));

const checksum = (letter: string) => `sha256:${letter.repeat(64)}`;
const artifact: ArtifactRefDto = makeArtifact({ artifact_id: "finding-1", run_id: "run-1", relative_path: "02_analysis/findings.json", checksum: checksum("a") });
const state = makeAuthoritativeRun({ run_id: "run-1", state_version: 3, artifacts: [artifact], source_angular_exact: "18.2.4", catalogue_version: "catalog-v1", runtime_candidates: [{ profile_id: "node-20-approved" }], registry_snapshot: { snapshot_id: "registry-1", checksum: checksum("e") } });
const response: FeasibilityResponse = {
  run_id: "run-1", resolution_id: "resolution-1", status: "feasible_with_warnings", source_exact: "18.2.4", source_family: "angular-18.x", target_family: "angular-21.x", support_level: "historical_experimental",
  route: ["19", "20", "21"].map((major, index) => ({ stage_id: `angular-${18 + index}-to-${major}`, source_family: `angular-${18 + index}.x`, target_family: `angular-${major}.x`, support_level: "historical_experimental", target_angular_exact: `${major}.0.0`, target_cli_exact: `${major}.0.0`, blockers: [], warnings: ["historical_fixture_evidence_incomplete"] })),
  selected_profile: { profile_id: "node-20-approved", angular_exact: "19.0.0", angular_cli_exact: "19.0.0", node_exact: "20.11.1", npm_exact: "10.2.4", npx_exact: "10.2.4", node_executable: "C:/node/node.exe", npm_executable: "C:/node/npm.cmd", npx_executable: "C:/node/npx.cmd", operating_system: "windows", architecture: "amd64", catalogue_version: "catalog-v1", source_angular_exact: "18.2.4", checksum: checksum("b") },
  blockers: [], warnings: ["historical_fixture_evidence_incomplete"], package: { artifact_set_checksum: checksum("c"), catalogue_version: "catalog-v1", workspace_fingerprint: "sha256:physical-workspace", plan_version: null }, package_checksum: checksum("d"), artifact_ids: ["catalogue-1", "route-1", "support-1", "registry-1", "profile-1", "package-1"], artifact_checksums: Object.fromEntries(["catalogue-1", "route-1", "support-1", "registry-1", "profile-1", "package-1"].map((id) => [id, checksum("e")])), artifact_links: Object.fromEntries(["catalogue-1", "route-1", "support-1", "registry-1", "profile-1", "package-1"].map((id) => [id, `/api/v1/artifacts/${id}`])), gate_id: "G05", gate_version: "g05-v1", gate_status: "pending", gate_decision: null, state_version: 5, event_sequence: 4, idempotent_replay: false,
};
const props = { runId: "run-1", initialState: state, connectionStatus: "open", artifacts: [artifact], workflowEvents: feasibilityPrerequisites, refreshAuthoritativeState: vi.fn().mockResolvedValue(undefined) };

describe("FeasibilityPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a subordinate heading when embedded in a pipeline stage", () => {
    render(<FeasibilityPanel {...props} headingLevel={4} />);
    expect(screen.getByRole("heading", { name: "Migration readiness", level: 4 })).toBeInTheDocument();
  });

  it("renders the authoritative ladder, support, exact profile, evidence, and G05 controls", async () => {
    vi.mocked(getFeasibility).mockResolvedValue(response);
    render(<FeasibilityPanel {...props} />);
    expect(await screen.findByText("Major-stage ladder")).toBeInTheDocument();
    expect(screen.getByText("angular-18.x → angular-19.x")).toBeInTheDocument();
    expect(screen.getByText("19.0.0 / 19.0.0")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "package-1" })).toHaveAttribute("href", "/api/v1/artifacts/package-1");
    expect(screen.getByRole("heading", { name: "Migration readiness" })).toBeInTheDocument();
  });

  it("renders empty state and reloads the authoritative snapshot after a stale resolve", async () => {
    vi.mocked(getFeasibility).mockRejectedValue(new ApiClientError("missing", 404));
    vi.mocked(queueFeasibilityResolution).mockRejectedValue(new ApiClientError("stale", 409));
    render(<FeasibilityPanel {...props} />);
    expect(await screen.findByText("No feasibility package is available yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolve route and Stage 1 profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The migration-readiness state is stale");
    expect(queueFeasibilityResolution).toHaveBeenCalledWith("run-1", { expected_state_version: 3, idempotency_key: expect.any(String) });
  });

  it("keeps the backend-owned resolution command actionable when derived inputs are absent", async () => {
    vi.mocked(getFeasibility).mockRejectedValue(new ApiClientError("missing", 404));
    vi.mocked(queueFeasibilityResolution).mockResolvedValue({ job_id: "planning-run-1", status: "queued_after_g04", current_step: "resolving_feasibility", correlation_id: "planning:run-1" });
    render(<FeasibilityPanel {...props} initialState={{ ...state, source_angular_exact: null, runtime_candidates: [], registry_snapshot: null } as unknown as AuthoritativeRunStateDto} />);

    const button = await screen.findByRole("button", { name: "Resolve route and Stage 1 profile" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(queueFeasibilityResolution).toHaveBeenCalledWith("run-1", { expected_state_version: 3, idempotency_key: expect.any(String) }));
  });

  it("offers authoritative regeneration when legacy feasibility lacks a workspace fingerprint", async () => {
    vi.mocked(getFeasibility).mockResolvedValue({ ...response, gate_status: "approved", package: { ...response.package, workspace_fingerprint: null } });
    vi.mocked(queueFeasibilityResolution).mockResolvedValue({ job_id: "planning-run-2", status: "queued_after_g04", current_step: "resolving_feasibility", correlation_id: "planning:run-1" });
    render(<FeasibilityPanel {...props} initialState={{ ...state, planning_job: { id: "planning-old", status: "technical_failed", current_step: "generating_plan", attempt: 2, max_attempts: 3, retryable: false, last_error_code: "PLANNING_WORKSPACE_FINGERPRINT_MISSING" } } as unknown as AuthoritativeRunStateDto} />);

    const button = await screen.findByRole("button", { name: "Regenerate fingerprint-bound feasibility" });
    fireEvent.click(button);

    await waitFor(() => expect(queueFeasibilityResolution).toHaveBeenCalledWith("run-1", { expected_state_version: 3, idempotency_key: expect.stringContaining("feasibility-rebind-run-1") }));
    expect(props.refreshAuthoritativeState).toHaveBeenCalled();
  });

  it("renders blocked state and keeps G05 unavailable", async () => {
    vi.mocked(getFeasibility).mockResolvedValue({ ...response, status: "blocked", blockers: ["NO_COMPATIBLE_STAGE1_PROFILE"], gate_status: "blocked" });
    render(<FeasibilityPanel {...props} />);
    expect(await screen.findByText("Feasibility is blocked; migration readiness cannot approve this route.")).toBeInTheDocument();
    expect(screen.getByText("NO_COMPATIBLE_STAGE1_PROFILE")).toBeInTheDocument();
    expect(screen.getByText("Migration readiness approval is blocked until the feasibility evidence is renewed.")).toBeInTheDocument();
  });

  it("renders backend failure guidance with the correlation ID", async () => {
    vi.mocked(getFeasibility).mockRejectedValue(new ApiClientError("failed", 503, "GET", "/feasibility", JSON.stringify({ correlation_id: "corr-failure" })));
    render(<FeasibilityPanel {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-failure");
  });

  it("requires a comment before approval with comment", async () => {
    vi.mocked(getFeasibility).mockResolvedValue(response);
    render(<FeasibilityPanel {...props} />);
    await screen.findByText("Major-stage ladder");
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "approve_with_comment" } });
    fireEvent.click(screen.getByRole("button", { name: "Record migration readiness decision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Add a comment");
    expect(decideG05).not.toHaveBeenCalled();
  });

  it("sends the complete G05 authority binding and preserves the draft on 409", async () => {
    vi.mocked(getFeasibility).mockResolvedValue(response);
    vi.mocked(decideG05).mockRejectedValue(new ApiClientError("stale", 409));
    render(<FeasibilityPanel {...props} />);

    await screen.findByText("Major-stage ladder");
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "approve_with_comment" } });
    fireEvent.change(screen.getByLabelText("Review comment"), { target: { value: "Preserve the feasibility draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Record migration readiness decision" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The migration-readiness state is stale");
    expect(decideG05).toHaveBeenCalledWith("run-1", {
      expected_state_version: 5,
      idempotency_key: expect.stringMatching(/^g05-run-1-/),
      gate_version: "g05-v1",
      package_checksum: checksum("d"),
      artifact_set_checksum: checksum("c"),
      workspace_fingerprint: "sha256:physical-workspace",
      plan_version: null,
      decision: "approve_with_comment",
      comment: "Preserve the feasibility draft",
    });
    expect(screen.getByLabelText("Review comment")).toHaveValue("Preserve the feasibility draft");
    expect(screen.queryByText(/Migration readiness was approved/)).not.toBeInTheDocument();
  });
});
