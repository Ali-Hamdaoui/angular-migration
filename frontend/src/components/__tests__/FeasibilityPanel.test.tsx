import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { decideG05, getFeasibility, resolveFeasibility } from "@/api/compatibility";
import { FeasibilityPanel } from "@/components/FeasibilityPanel";
import type { FeasibilityResponse } from "@/types/compatibility";
import type { ArtifactRefDto, AuthoritativeRunStateDto } from "@/types/generated/api";

vi.mock("@/api/compatibility", () => ({ getFeasibility: vi.fn(), resolveFeasibility: vi.fn(), decideG05: vi.fn() }));

const checksum = (letter: string) => `sha256:${letter.repeat(64)}`;
const artifact: ArtifactRefDto = { artifact_id: "finding-1", run_id: "run-1", stage_id: null, artifact_type: "json", relative_path: "02_analysis/findings.json", created_at: "now", checksum: checksum("a") };
const state = { run_id: "run-1", state_version: 3, artifacts: [artifact] } as unknown as AuthoritativeRunStateDto;
const response: FeasibilityResponse = {
  run_id: "run-1", resolution_id: "resolution-1", status: "feasible_with_warnings", source_exact: "18.2.4", source_family: "angular-18.x", target_family: "angular-21.x", support_level: "historical_experimental",
  route: ["19", "20", "21"].map((major, index) => ({ stage_id: `angular-${18 + index}-to-${major}`, source_family: `angular-${18 + index}.x`, target_family: `angular-${major}.x`, support_level: "historical_experimental", target_angular_exact: `${major}.0.0`, target_cli_exact: `${major}.0.0`, blockers: [], warnings: ["historical_fixture_evidence_incomplete"] })),
  selected_profile: { profile_id: "node-20-approved", angular_exact: "19.0.0", angular_cli_exact: "19.0.0", node_exact: "20.11.1", npm_exact: "10.2.4", npx_exact: "10.2.4", node_executable: "C:/node/node.exe", npm_executable: "C:/node/npm.cmd", npx_executable: "C:/node/npx.cmd", operating_system: "windows", architecture: "amd64", catalogue_version: "catalog-v1", source_angular_exact: "18.2.4", checksum: checksum("b") },
  blockers: [], warnings: ["historical_fixture_evidence_incomplete"], package: { artifact_set_checksum: checksum("c"), catalogue_version: "catalog-v1", workspace_fingerprint: null, plan_version: null }, package_checksum: checksum("d"), artifact_ids: ["catalogue-1", "route-1", "support-1", "registry-1", "profile-1", "package-1"], artifact_checksums: Object.fromEntries(["catalogue-1", "route-1", "support-1", "registry-1", "profile-1", "package-1"].map((id) => [id, checksum("e")])), artifact_links: Object.fromEntries(["catalogue-1", "route-1", "support-1", "registry-1", "profile-1", "package-1"].map((id) => [id, `/api/v1/artifacts/${id}`])), gate_id: "G05", gate_version: "g05-v1", gate_status: "pending", gate_decision: null, state_version: 5, event_sequence: 4, idempotent_replay: false,
};
const props = { runId: "run-1", initialState: state, connectionStatus: "open", artifacts: [artifact], workflowEvents: [], refreshAuthoritativeState: vi.fn().mockResolvedValue(undefined) };

describe("FeasibilityPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the authoritative ladder, support, exact profile, evidence, and G05 controls", async () => {
    vi.mocked(getFeasibility).mockResolvedValue(response);
    render(<FeasibilityPanel {...props} />);
    expect(await screen.findByText("Major-stage ladder")).toBeInTheDocument();
    expect(screen.getByText("angular-18.x → angular-19.x")).toBeInTheDocument();
    expect(screen.getByText("19.0.0 / 19.0.0")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "package-1" })).toHaveAttribute("href", "/api/v1/artifacts/package-1");
    expect(screen.getByRole("heading", { name: "G05: pending" })).toBeInTheDocument();
  });

  it("renders empty state and reloads the authoritative snapshot after a stale resolve", async () => {
    vi.mocked(getFeasibility).mockRejectedValue(new ApiClientError("missing", 404));
    vi.mocked(resolveFeasibility).mockRejectedValue(new ApiClientError("stale", 409));
    render(<FeasibilityPanel {...props} />);
    expect(await screen.findByText("No feasibility package is available yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolve route and Stage 1 profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("feasibility or G05 state is stale");
    expect(resolveFeasibility).toHaveBeenCalledWith("run-1", expect.objectContaining({ expected_state_version: 3, prerequisite_artifacts: [{ artifact_id: "finding-1", checksum: checksum("a") }] }));
  });

  it("renders blocked state and keeps G05 unavailable", async () => {
    vi.mocked(getFeasibility).mockResolvedValue({ ...response, status: "blocked", blockers: ["NO_COMPATIBLE_STAGE1_PROFILE"], gate_status: "blocked" });
    render(<FeasibilityPanel {...props} />);
    expect(await screen.findByText("Feasibility is blocked; G05 cannot approve this route.")).toBeInTheDocument();
    expect(screen.getByText("NO_COMPATIBLE_STAGE1_PROFILE")).toBeInTheDocument();
    expect(screen.getByText("G05 is blocked until the feasibility evidence is renewed.")).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "Record G05 decision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Add a comment");
    expect(decideG05).not.toHaveBeenCalled();
  });
});
