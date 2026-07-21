import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiClientError } from "@/api/client";
import { G08ReviewWorkspace } from "@/components/G08ReviewWorkspace";
import type { G08ReviewResponse } from "@/types/transformation";

const getG08Approval = vi.fn();
const initializeG08 = vi.fn();
const decideG08 = vi.fn();

vi.mock("@/api/transformations", () => ({
  getG08Approval: (...args: unknown[]) => getG08Approval(...args),
  initializeG08: (...args: unknown[]) => initializeG08(...args),
  decideG08: (...args: unknown[]) => decideG08(...args),
}));

const review: G08ReviewResponse = {
  run_id: "run-1",
  stage_id: "stage-1",
  gate_id: "G08",
  gate_version: "g08-v1",
  status: "pending",
  package: {
    run_id: "run-1",
    stage_id: "stage-1",
    gate_id: "G08",
    gate_version: "g08-v1",
    state_version: 7,
    actor: "reviewer",
    transformation_record_id: "update-1",
    evidence_id: "evidence-1",
    plan_version: 2,
    plan_checksum: "sha256:plan",
    transformation_result: { update_status: "succeeded", target_version_status: "verified", resolved_target_version: "21.0.0" },
    evidence_result: { overall_risk_level: "low", evidence_complete: true, total_files_changed: 3 },
    artifact_refs: [{ artifact_id: "diff-1", run_id: "run-1", stage_id: "stage-1", artifact_type: "json", relative_path: "diff.json", created_at: "2026-07-20T10:00:00Z", checksum: "sha256:diff" }],
    artifact_set_checksum: "sha256:artifacts",
    workspace_fingerprint: "sha256:workspace",
    technical_blockers: [],
    package_checksum: "sha256:package",
  },
  package_checksum: "sha256:package",
  artifact_set_checksum: "sha256:artifacts",
  workspace_fingerprint: "sha256:workspace",
  plan_version: 2,
  plan_checksum: "sha256:plan",
  artifact_ids: ["diff-1", "g08-package-1"],
  artifact_links: { "diff-1": "/api/v1/artifacts/diff-1", "g08-package-1": "/api/v1/artifacts/g08-package-1" },
  package_artifact_id: "g08-package-1",
  technical_blockers: [],
  state_version: 7,
  event_sequence: 11,
  idempotent_replay: false,
  correlation_id: "corr-1",
};

describe("G08ReviewWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "uuid-1" });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders the immutable evidence package and submits an exact-bound approval", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    getG08Approval.mockResolvedValue(review);
    decideG08.mockResolvedValue({ ...review, status: "approved", decision: "approved", state_version: 8 });

    render(<G08ReviewWorkspace runId="run-1" stageId="stage-1" gateId="G08" expectedStateVersion={6} connectionStatus="open" onAuthoritativeRefresh={refresh} />);

    expect(await screen.findByTitle("sha256:workspace")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download/ })).toHaveAttribute("href", "http://127.0.0.1:8000/api/v1/runs/run-1/artifacts/diff-1");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => expect(decideG08).toHaveBeenCalledWith("run-1", "stage-1", "G08", expect.objectContaining({
      expected_state_version: 7,
      gate_version: "g08-v1",
      package_checksum: "sha256:package",
      artifact_set_checksum: "sha256:artifacts",
      workspace_fingerprint: "sha256:workspace",
      plan_version: 2,
      plan_checksum: "sha256:plan",
      decision: "approved",
    })));
    expect(refresh).toHaveBeenCalled();
    expect((await screen.findAllByText("approved")).length).toBeGreaterThanOrEqual(1);
  });

  it("submits modification_requested rather than converting it to approval", async () => {
    getG08Approval.mockResolvedValue(review);
    decideG08.mockResolvedValue({ ...review, status: "modification_requested", decision: "modification_requested", comment: "Keep the public API." });

    render(<G08ReviewWorkspace runId="run-1" stageId="stage-1" gateId="G08" expectedStateVersion={6} />);
    await screen.findByText("Transformation Summary");
    fireEvent.click(screen.getByRole("button", { name: "Request Changes" }));
    fireEvent.change(screen.getByLabelText("Decision comment"), { target: { value: "Keep the public API." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit Change Request" }));

    await waitFor(() => expect(decideG08).toHaveBeenCalledWith("run-1", "stage-1", "G08", expect.objectContaining({ decision: "modification_requested", comment: "Keep the public API." })));
  });

  it("distinguishes missing, authorization, stale, and backend failure states", async () => {
    getG08Approval.mockRejectedValueOnce(new ApiClientError("missing", 404));
    const { rerender } = render(<G08ReviewWorkspace runId="run-1" stageId="stage-1" gateId="G08" expectedStateVersion={6} />);
    expect(await screen.findByText("No review package has been initialized yet.")).toBeInTheDocument();

    getG08Approval.mockRejectedValueOnce(new ApiClientError("forbidden", 403, "GET", "/g08", JSON.stringify({ error_code: "FORBIDDEN", message: "Forbidden", correlation_id: "corr-auth" })));
    rerender(<G08ReviewWorkspace runId="run-2" stageId="stage-1" gateId="G08" expectedStateVersion={6} />);
    expect(await screen.findByText("Authorization Error")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("corr-auth"))).toBeInTheDocument();

    getG08Approval.mockRejectedValueOnce(new ApiClientError("stale", 409, "GET", "/g08", JSON.stringify({ error_code: "STALE_STATE_VERSION", message: "Stale state", correlation_id: "corr-stale" })));
    rerender(<G08ReviewWorkspace runId="run-3" stageId="stage-1" gateId="G08" expectedStateVersion={6} />);
    expect(await screen.findByRole("button", { name: "Generate Current Review Package" })).toBeInTheDocument();

    getG08Approval.mockRejectedValueOnce(new ApiClientError("failed", 500, "GET", "/g08", JSON.stringify({ error_code: "INTERNAL", message: "Backend failed", correlation_id: "corr-fail" })));
    rerender(<G08ReviewWorkspace runId="run-4" stageId="stage-1" gateId="G08" expectedStateVersion={6} />);
    expect(await screen.findByText("Backend failed")).toBeInTheDocument();
  });

  it("blocks approval controls when the backend reports technical blockers", async () => {
    getG08Approval.mockResolvedValue({ ...review, technical_blockers: ["target Angular version is not verified"], package: { ...review.package, technical_blockers: ["target Angular version is not verified"] } });
    render(<G08ReviewWorkspace runId="run-1" stageId="stage-1" gateId="G08" expectedStateVersion={6} />);

    expect(await screen.findByText("target Angular version is not verified")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Approve with Comment" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Request Changes" })).toBeEnabled();
  });

  it("initializes with a package request rather than a fake decision", async () => {
    getG08Approval.mockRejectedValue(new ApiClientError("missing", 404));
    initializeG08.mockResolvedValue(review);
    render(<G08ReviewWorkspace runId="run-1" stageId="stage-1" gateId="G08" expectedStateVersion={6} />);

    fireEvent.click(await screen.findByRole("button", { name: "Initialize Review Package" }));
    await waitFor(() => expect(initializeG08).toHaveBeenCalledWith("run-1", "stage-1", "G08", {
      expected_state_version: 6,
      idempotency_key: "g08-init-uuid-1",
      gate_id: "G08",
    }));
  });
});
