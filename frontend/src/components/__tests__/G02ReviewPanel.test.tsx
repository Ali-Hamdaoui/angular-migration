import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { G02ReviewPanel } from "@/components/G02ReviewPanel";
import { BaselineQualificationPanel } from "@/components/BaselineQualificationPanel";
import { decideG02, getG02Review } from "@/api/g02";
import { decideG03, getBaselineSummary } from "@/api/baselineG03";
import { ApiClientError } from "@/api/client";
import type { BaselineAssessmentResponse, G02ReviewResponse } from "@/types/generated/api";

vi.mock("@/api/g02", () => ({ getG02Review: vi.fn(), decideG02: vi.fn() }));
vi.mock("@/api/baselineG03", () => ({ getBaselineSummary: vi.fn(), decideG03: vi.fn(), qualifyBaseline: vi.fn() }));

const state = { run_id: "run-1", status: "SOURCE_VALIDATED", run_phase: "PREFLIGHT_SNAPSHOT", phase_status: "running", approval_status: "pending", state_version: 4, preflight_id: "p1", source_path: "C:/source", target_output_path: "C:/target", graph_thread_id: "thread-1", created_at: "2026-01-01", updated_at: "2026-01-01", artifacts: [], workflow_events: [] } as never;
const review = { run_id: "run-1", gate_id: "G02", gate_version: "g02-v1", status: "pending", decision: null, package: { run_id: "run-1", gate_id: "G02", gate_version: "g02-v1", state_version: 4, actor: "operator", policy_version: "source-snapshot-policy-v1", snapshot_id: "snapshot-1", source_fingerprint: "sha256:source", snapshot_fingerprint: "sha256:snapshot", artifact_set_checksum: "sha256:artifacts", artifacts: [], integrity: { before_fingerprint: "sha256:source", after_snapshot_fingerprint: "sha256:source", snapshot_fingerprint: "sha256:snapshot", manifest_checksum: "manifest-1", policy_version: "source-snapshot-policy-v1", source_read_only_verified: true }, package_checksum: "sha256:package" }, baseline_input_boundary: null, state_version: 4, event_sequence: 6, idempotent_replay: false, stale_reason: null, comment: null } as unknown as G02ReviewResponse;

describe("G02ReviewPanel", () => {
  it("renders a subordinate heading when embedded in a pipeline stage", () => {
    render(<G02ReviewPanel runId="run-1" initialState={state} authoritativeReview={{ status: "ready", value: review }} headingLevel={4} />);
    expect(screen.getByRole("heading", { name: "G02 source-integrity boundary", level: 4 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Immutable evidence", level: 5 })).toBeInTheDocument();
    expect(getG02Review).not.toHaveBeenCalled();
  });

  it("shows the blocked next step and records approval", async () => {
    vi.mocked(getG02Review).mockResolvedValue(review);
    vi.mocked(decideG02).mockResolvedValue({ ...(review as Record<string, unknown>), status: "approved", decision: "approved", baseline_input_boundary: "snapshot-1" } as never);
    render(<G02ReviewPanel runId="run-1" initialState={state} />);

    expect(await screen.findByText(/evidence is finalized and verified/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Record G02 decision" }));
    await waitFor(() => expect(decideG02).toHaveBeenCalledWith("run-1", {
      expected_state_version: 4,
      idempotency_key: "g02-run-1-approved-sha256:package",
      actor: "control-tower",
      decision: "approved",
      comment: null,
      gate_id: "G02",
    }));
    expect(await screen.findByText(/Baseline input boundary/)).toBeInTheDocument();
  });

  it("keeps an embedded successful decision closed while the authoritative binding catches up", async () => {
    const approvedReview = { ...(review as Record<string, unknown>), status: "approved", decision: "approved", baseline_input_boundary: "snapshot-1", state_version: 5, event_sequence: 7 } as unknown as G02ReviewResponse;
    vi.mocked(decideG02).mockResolvedValue(approvedReview);
    const view = render(<G02ReviewPanel runId="run-1" initialState={state} authoritativeReview={{ status: "ready", value: review }} />);

    fireEvent.click(screen.getByRole("button", { name: "Record G02 decision" }));

    expect(await screen.findByText(/Baseline input boundary/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record G02 decision" })).not.toBeInTheDocument();
    view.rerender(<G02ReviewPanel runId="run-1" initialState={state} authoritativeReview={{ status: "ready", value: review }} />);
    expect(screen.queryByRole("button", { name: "Record G02 decision" })).not.toBeInTheDocument();
    view.rerender(<G02ReviewPanel runId="run-1" initialState={state} authoritativeReview={{ status: "loading" }} />);
    expect(screen.getByText("Loading G02 review package")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record G02 decision" })).not.toBeInTheDocument();
  });

  it.each([
    ["malformed identity", {
      ...(review as Record<string, unknown>),
      run_id: "wrong-run",
      status: "approved",
      decision: "approved",
      baseline_input_boundary: "wrong-snapshot",
      state_version: 5,
      event_sequence: 7,
      package: {
        ...review.package,
        run_id: "wrong-run",
        gate_id: "G04",
        package_checksum: "sha256:wrong-package",
        artifacts: [{ artifact_id: "wrong-artifact", run_id: "wrong-run", stage_id: null, artifact_type: "json", relative_path: "global/wrong-artifact.json", created_at: "2026-01-01", checksum: "sha256:wrong-artifact" }],
      },
    }],
    ["non-monotonic version", {
      ...(review as Record<string, unknown>),
      status: "approved",
      decision: "approved",
      baseline_input_boundary: "snapshot-1",
      state_version: 3,
      event_sequence: 5,
    }],
  ])("rejects a %s G02 decision response and waits for authoritative refresh", async (_case, response) => {
    const refreshAuthoritativeState = vi.fn().mockResolvedValue(undefined);
    vi.mocked(decideG02).mockResolvedValue(response as unknown as G02ReviewResponse);
    render(<G02ReviewPanel runId="run-1" initialState={state} authoritativeReview={{ status: "ready", value: review }} refreshAuthoritativeState={refreshAuthoritativeState} />);

    fireEvent.click(screen.getByRole("button", { name: "Record G02 decision" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("G02 decision response could not be validated");
    expect(refreshAuthoritativeState).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Record G02 decision" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Baseline input boundary/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "global/wrong-artifact.json" })).not.toBeInTheDocument();
  });

  it("keeps a validated modification request closed until a new authoritative package arrives", async () => {
    vi.mocked(decideG02).mockResolvedValue({
      ...(review as Record<string, unknown>),
      status: "modification_requested",
      decision: "modification_requested",
      state_version: 5,
      event_sequence: 7,
    } as unknown as G02ReviewResponse);
    render(<G02ReviewPanel runId="run-1" initialState={state} authoritativeReview={{ status: "ready", value: review }} />);

    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "modification_requested" } });
    fireEvent.click(screen.getByRole("button", { name: "Record G02 decision" }));

    expect(await screen.findByText("G02 is modification_requested; the workflow will not continue until a new valid evidence package is created.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record G02 decision" })).not.toBeInTheDocument();
  });

  it("fails closed on a stale G02 decision and preserves the reviewer draft", async () => {
    vi.mocked(getG02Review).mockResolvedValue(review);
    vi.mocked(decideG02).mockRejectedValue(new ApiClientError("stale", 409));
    render(<G02ReviewPanel runId="run-1" initialState={state} />);

    await screen.findByText(/evidence is finalized and verified/);
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "approved_with_comment" } });
    fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Keep this review draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Record G02 decision" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("G02 is stale");
    expect(screen.getByLabelText("Comment")).toHaveValue("Keep this review draft");
    expect(screen.queryByText(/Baseline input boundary: immutable snapshot/)).not.toBeInTheDocument();
  });

  it("keeps the decision disabled while integrity evidence is not verified", async () => {
    vi.mocked(getG02Review).mockResolvedValue({ ...review, package: { ...review.package, integrity: { ...review.package.integrity, source_read_only_verified: false } } });
    render(<G02ReviewPanel runId="run-1" initialState={state} />);

    const button = await screen.findByRole("button", { name: "Record G02 decision" });
    expect(button).toBeDisabled();
    expect(screen.getByText(/blocked while source-integrity evidence is being finalized/)).toBeInTheDocument();
  });
});

describe("BaselineQualificationPanel G03 authority", () => {
  const assessment: BaselineAssessmentResponse = {
    run_id: "run-1",
    assessment_id: "assessment-1",
    status: "qualified",
    policy: "strict_clean",
    policy_version: "baseline-v1",
    blockers: [],
    warnings: [],
    known_failures: [],
    evidence_confidence: {},
    evidence_set_checksum: "sha256:evidence",
    sandbox_fingerprint: "sha256:workspace",
    execution_profile_checksum: "sha256:profile",
    package_checksum: "sha256:g03-package",
    artifact_ids: ["baseline-package"],
    state_version: 8,
    event_sequence: 11,
    g03_decision: null,
    stale_reason: null,
    idempotent_replay: false,
  };

  it("renders a subordinate heading when embedded in a pipeline stage", () => {
    render(<BaselineQualificationPanel runId="run-1" stateVersion={7} authoritativeAssessment={{ status: "ready", value: assessment }} headingLevel={4} />);
    expect(screen.getByRole("heading", { name: "Baseline qualification / G03", level: 4 })).toBeInTheDocument();
    expect(getBaselineSummary).not.toHaveBeenCalled();
  });

  it("keeps the G03 decision bound to its authoritative assessment version", async () => {
    vi.mocked(getBaselineSummary).mockResolvedValue(assessment);
    vi.mocked(decideG03).mockResolvedValue({ ...assessment, g03_decision: "approved" });
    render(<BaselineQualificationPanel runId="run-1" stateVersion={7} workflowEvents={[{ event_type: "G03_CREATED" }]} />);

    fireEvent.click(await screen.findByRole("button", { name: "Approve G03" }));

    await waitFor(() => expect(decideG03).toHaveBeenCalledWith("run-1", {
      expected_state_version: 8,
      idempotency_key: expect.stringMatching(/^g03-\d+$/),
      actor: "reviewer",
      decision: "approved",
    }));
  });
});
