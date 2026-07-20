import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AngularUpdatePanel } from "../AngularUpdatePanel";

vi.mock("@/api/transformations", () => ({ getAngularUpdate: vi.fn(), getTargetVersionTyped: vi.fn(), getTransformationEvidence: vi.fn(), startAngularUpdate: vi.fn(), verifyTargetVersion: vi.fn() }));
vi.mock("@/api/plans", () => ({ getStagePlan: vi.fn() }));
vi.mock("@/api/executionProfiles", () => ({ getExecutionProfiles: vi.fn() }));
import { getAngularUpdate, getTargetVersionTyped, getTransformationEvidence, startAngularUpdate } from "@/api/transformations";
import { getStagePlan } from "@/api/plans";
import { getExecutionProfiles } from "@/api/executionProfiles";

const base = { run_id: "run-1", stage_id: "stage-1", target_version_status: "inconclusive", resolved_target_version: null, command_execution_id: "exec-1", artifact_ids: ["artifact-1"], state_version: 2, event_sequence: 2, idempotent_replay: false };
const plan = { stage_plan: { stage_id: "stage-1", source_exact: "17.0.0", target_exact: "18.0.0", execution_profile_id: "profile-1", commands: { angular_update: [{ command_id: "angular-update", executable: "npx", arguments: ["--no-install", "ng", "update", "@angular/core@18.0.0"], shell: false, working_directory_alias: "stage_workspace", timeout_seconds: 300, network_profile: "none", conditional: false }] } } };
const profile = { profile_id: "profile-1", node_exact: "20.11.1", package_manager_exact: "10.2.4", npx_exact: "10.2.4", checksum: "sha256:profile" };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getStagePlan).mockResolvedValue(plan as never);
  vi.mocked(getExecutionProfiles).mockResolvedValue({ selected_profile: profile, compatible_profiles: [], status: "selected" } as never);
  vi.mocked(getTransformationEvidence).mockResolvedValue({ migration_list: ["migration-1"], artifact_ids: ["artifact-2"] } as never);
  vi.mocked(getTargetVersionTyped).mockResolvedValue({ target_version_status: "inconclusive", resolved_target_version: null, evidence_sources: { package_json_version: "18.0.0", lockfile_version: "18.0.0", dependency_tree_version: "18.0.0", ng_version_output: "18.0.0" }, all_sources_agree: true, disagreements: [], artifact_ids: [] } as never);
});

function renderPanel(overrides: Record<string, unknown> = {}) { return render(<AngularUpdatePanel runId="run-1" stageId="stage-1" expectedStateVersion={2} {...overrides} />); }

describe("AngularUpdatePanel", () => {
  it("renders the locked command, profile, evidence matrix and artifact links", async () => {
    vi.mocked(getAngularUpdate).mockResolvedValue(base as never);
    renderPanel();
    expect(await screen.findByText("Start Angular update")).toBeInTheDocument();
    expect(screen.getByText(/npx --no-install ng update/)).toBeInTheDocument();
    expect(screen.getByText("profile-1")).toBeInTheDocument();
    expect(screen.getByText("migration-1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "artifact-1" })).toHaveAttribute("href", "/api/v1/artifacts/artifact-1");
  });

  it("never treats succeeded without backend verification as pass", async () => {
    vi.mocked(getAngularUpdate).mockResolvedValue({ ...base, status: "succeeded" } as never);
    renderPanel();
    expect(await screen.findByText(/awaiting TARGET_VERSION_VERIFIED/)).toBeInTheDocument();
    expect(screen.queryByText("PASSED")).not.toBeInTheDocument();
  });

  it("passes only on TARGET_VERSION_VERIFIED SSE", async () => {
    vi.mocked(getAngularUpdate).mockReturnValue(new Promise(() => {}) as never);
    const view = renderPanel({ workflowEvents: [{ event_id: "evt-1", run_id: "run-1", stage_id: "stage-1", event_type: "ANGULAR_UPDATE_COMPLETED", occurred_at: "now", sequence: 1, payload: {} }] });
    expect(await screen.findByText(/awaiting TARGET_VERSION_VERIFIED/)).toBeInTheDocument();
    view.rerender(<AngularUpdatePanel runId="run-1" stageId="stage-1" expectedStateVersion={2} workflowEvents={[{ event_id: "evt-1", run_id: "run-1", stage_id: "stage-1", event_type: "ANGULAR_UPDATE_COMPLETED", occurred_at: "now", sequence: 1, payload: {} }, { event_id: "evt-2", run_id: "run-1", stage_id: "stage-1", event_type: "TARGET_VERSION_VERIFIED", occurred_at: "now", sequence: 2, payload: { state_version: 3 } }]} />);
    expect(await screen.findByText("PASSED")).toBeInTheDocument();
  });

  it("renders blocked, cancelled, stale and missing evidence states", async () => {
    vi.mocked(getAngularUpdate).mockRejectedValueOnce(new Error("missing"));
    renderPanel({ workflowEvents: [{ event_id: "evt-3", run_id: "run-1", stage_id: "stage-1", event_type: "INTERACTIVE_DECISION_REQUIRED", occurred_at: "now", sequence: 3, payload: {} }] });
    expect(await screen.findByRole("alert")).toHaveTextContent(/Interactive prompt/);
  });

  it("prevents duplicate start requests", async () => {
    vi.mocked(getAngularUpdate).mockResolvedValue(base as never);
    vi.mocked(startAngularUpdate).mockReturnValue(new Promise(() => {}) as never);
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Start Angular update" }));
    expect(startAngularUpdate).toHaveBeenCalledTimes(1);
  });

  it("does not expose an edit control for versions or commands", async () => {
    vi.mocked(getAngularUpdate).mockResolvedValue(base as never);
    renderPanel();
    await screen.findByText("Start Angular update");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Angular Update" })).toBeInTheDocument();
  });
});
