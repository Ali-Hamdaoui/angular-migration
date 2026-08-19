import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { BaselineQualificationPanel } from "@/components/BaselineQualificationPanel";
import { decideG03, getBaselineSummary, qualifyBaseline } from "@/api/baselineG03";
import { getBaselineValidation } from "@/api/baselineMatrix";
import { captureBaselineParity } from "@/api/baselineParity";
import { applyBaselineRepair } from "@/api/baselineRepair";
import { getAuthoritativeRunState } from "@/api/runs";
import { ApiClientError } from "@/api/client";
import type { BaselineParityResponse } from "@/types/baselineParity";
import type { BaselineValidationResponse } from "@/types/baselineMatrix";
import type { BaselineAssessmentResponse } from "@/types/generated/api";

vi.mock("@/api/baselineG03", () => ({ getBaselineSummary: vi.fn(), decideG03: vi.fn(), qualifyBaseline: vi.fn() }));
vi.mock("@/api/baselineMatrix", () => ({ getBaselineValidation: vi.fn() }));
vi.mock("@/api/baselineParity", () => ({ captureBaselineParity: vi.fn() }));
vi.mock("@/api/baselineRepair", () => ({ applyBaselineRepair: vi.fn() }));
vi.mock("@/api/runs", () => ({ getAuthoritativeRunState: vi.fn() }));

const blockedAssessment: BaselineAssessmentResponse = {
  run_id: "run-1",
  assessment_id: "assessment-1",
  status: "blocked_by_environment",
  policy: "strict_clean",
  policy_version: "baseline-v1",
  blockers: ["BASELINE_REQUIRED_TEST_NOT_PROVEN", "KNOWN_BASELINE_FAILURES_REQUIRE_POLICY"],
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

const staleAssessment: BaselineAssessmentResponse = {
  ...blockedAssessment,
  status: "stale",
  stale_reason: "BASELINE-TEST-001 was applied; baseline validation, parity, and G03 must be regenerated.",
};

const qualifiedWithKnownFailures: BaselineAssessmentResponse = {
  ...blockedAssessment,
  status: "qualified_with_known_failures",
  policy: "qualified_known_failures",
  blockers: [],
  warnings: ["BASELINE_HAS_APPROVED_KNOWN_FAILURES"],
  known_failures: [{ kind: "lint", fingerprint: "sha256:f1", origin: "pre-existing" }],
  g03_decision: null,
  state_version: 30,
  event_sequence: 40,
};

function validation(kind: "build" | "test" | "lint", status: string, testCount: number | null, eventSequence = 20): BaselineValidationResponse {
  return {
    validation_id: `v-${kind}`,
    run_id: "run-1",
    kind,
    status: status as BaselineValidationResponse["status"],
    targets: [],
    results: [{ target_id: `${kind}-target`, kind, status: status as never, exit_code: 0, duration_ms: null, warnings: [], test_count: testCount, failed_tests: [], output_location: null, artifact_ids: [], blocker: null }],
    parser_summary: null,
    artifact_ids: [],
    artifact_checksums: {},
    baseline_checksum: null,
    state_version: 10,
    event_sequence: eventSequence,
    idempotent_replay: false,
  };
}

const testPassed = validation("test", "passed", 1);
const testZeroCount = validation("test", "passed", 0);
const testFailed = validation("test", "failed", 0);
const lintFailed = validation("lint", "failed", null);
const lintPassed = validation("lint", "passed", null);
const buildPassed = validation("build", "passed", null);
const buildFailed = validation("build", "failed", null);

function parityWith(failures: BaselineParityResponse["failures"]): BaselineParityResponse {
  return {
    run_id: "run-1",
    evidence_id: "parity-1",
    status: "captured",
    schema_version: "baseline-parity-v1",
    parser_version: "baseline-parsers-v1",
    baseline_checksum: "sha256:baseline",
    runtime_profile_id: null,
    runtime_checksum: null,
    failures,
    routes: [],
    backend_integration: {},
    anchors: [],
    confidence: {},
    source_artifact_ids: [],
    artifact_ids: [],
    artifact_checksums: {},
    state_version: 22,
    event_sequence: 30,
    idempotent_replay: false,
  };
}

const lintFailureOnly = parityWith([{ fingerprint: "sha256:f1", group: "lint:failure", kind: "lint", message: "lint error", origin: "pre-existing", severity: "error", count: 2, confidence: "machine_proven", parser_version: "baseline-parsers-v1", schema_version: "baseline-parity-v1" }]);
const testFailureParity = parityWith([{ fingerprint: "sha256:f2", group: "test:failure", kind: "test", message: "spec failed", origin: "pre-existing", severity: "error", count: 1, confidence: "machine_proven", parser_version: "baseline-parsers-v1", schema_version: "baseline-parity-v1" }]);

const runState = (version: number) => ({ state_version: version }) as never;
const repairResponse = { run_id: "run-1", recipe_id: "BASELINE-TEST-001", attempt_id: "attempt-1", status: "applied", g03_package_checksum: "sha256:g03-package", proposal_checksum: "sha256:p", pre_fingerprint: "sha256:pre", post_fingerprint: "sha256:post", artifact_ids: ["a1"], state_version: 10, event_sequence: 16, idempotent_replay: false };

function renderPanel(assessment: BaselineAssessmentResponse, workflowEvents: Array<{ event_type: string; sequence?: number }> = []) {
  const refreshAuthoritativeState = vi.fn().mockResolvedValue(undefined);
  const view = render(<BaselineQualificationPanel runId="run-1" stateVersion={8} workflowEvents={workflowEvents} refreshAuthoritativeState={refreshAuthoritativeState} authoritativeAssessment={{ status: "ready", value: assessment }} headingLevel={4} />);
  return { refreshAuthoritativeState, view };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getBaselineSummary).mockResolvedValue(blockedAssessment);
  vi.mocked(getBaselineValidation).mockImplementation((_runId: string, kind: string) => Promise.resolve(kind === "test" ? testPassed : kind === "lint" ? lintFailed : buildPassed));
  vi.mocked(getAuthoritativeRunState).mockResolvedValue(runState(8));
  vi.mocked(decideG03).mockResolvedValue(blockedAssessment);
  vi.mocked(applyBaselineRepair).mockResolvedValue(repairResponse);
  vi.mocked(captureBaselineParity).mockResolvedValue(lintFailureOnly);
  vi.mocked(qualifyBaseline).mockResolvedValue(qualifiedWithKnownFailures);
});

describe("BaselineQualificationPanel governed baseline recovery", () => {
  it("exposes the governed repair action when the current assessment carries BASELINE_REQUIRED_TEST_NOT_PROVEN", async () => {
    renderPanel(blockedAssessment);
    expect(await screen.findByRole("button", { name: "Repair baseline test" })).toBeInTheDocument();
    expect(screen.getByText(/BASELINE-TEST-001 baseline repair/)).toBeInTheDocument();
  });

  it("repairs through the current G03 package and state bindings, requests changes, and never auto-approves G03", async () => {
    vi.mocked(getBaselineSummary)
      .mockResolvedValueOnce(blockedAssessment)
      .mockResolvedValueOnce(staleAssessment);
    vi.mocked(getAuthoritativeRunState)
      .mockResolvedValueOnce(runState(8))
      .mockResolvedValueOnce(runState(9));
    const { refreshAuthoritativeState } = renderPanel(blockedAssessment);

    fireEvent.click(await screen.findByRole("button", { name: "Repair baseline test" }));

    await waitFor(() => expect(applyBaselineRepair).toHaveBeenCalledWith("run-1", {
      expected_state_version: 9,
      idempotency_key: expect.stringMatching(/^baseline-repair-run-1-\d+$/),
      actor: "control-tower",
      recipe_id: "BASELINE-TEST-001",
      g03_package_checksum: "sha256:g03-package",
    }));
    expect(decideG03).toHaveBeenCalledWith("run-1", {
      expected_state_version: 8,
      idempotency_key: expect.stringMatching(/^g03-repair-run-1-\d+$/),
      actor: "control-tower",
      decision: "modification_requested",
      comment: expect.stringContaining("BASELINE-TEST-001"),
    });
    expect(decideG03).not.toHaveBeenCalledWith(expect.objectContaining({ decision: "approved" }));
    expect(refreshAuthoritativeState).toHaveBeenCalled();
    expect(await screen.findByText(/fresh baseline test and lint validation is now required/i)).toBeInTheDocument();
    expect(screen.getByText(/G03 package is stale/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Repair baseline test" })).not.toBeInTheDocument();
  });

  it("fails closed when the backend rejects the repair", async () => {
    vi.mocked(applyBaselineRepair).mockRejectedValue(new ApiClientError("stale", 409));
    const { refreshAuthoritativeState } = renderPanel(blockedAssessment);

    fireEvent.click(await screen.findByRole("button", { name: "Repair baseline test" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("stale");
    expect(refreshAuthoritativeState).toHaveBeenCalled();
    expect(screen.queryByText(/fresh baseline test and lint validation is now required/i)).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Repair baseline test" })).toBeInTheDocument();
  });

  it("fails closed when the blocker is no longer present in the current assessment", async () => {
    vi.mocked(getBaselineSummary).mockResolvedValue({ ...blockedAssessment, blockers: ["KNOWN_BASELINE_FAILURES_REQUIRE_POLICY"] });
    renderPanel(blockedAssessment);

    fireEvent.click(await screen.findByRole("button", { name: "Repair baseline test" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("no longer present");
    expect(decideG03).not.toHaveBeenCalled();
    expect(applyBaselineRepair).not.toHaveBeenCalled();
  });

  it("does not offer any lint repair for known pre-existing lint failures", async () => {
    renderPanel({ ...blockedAssessment, blockers: ["KNOWN_BASELINE_FAILURES_REQUIRE_POLICY"] });
    expect(await screen.findByRole("button", { name: "Accept documented baseline defects" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Repair baseline test" })).not.toBeInTheDocument();
    expect(screen.queryByText(/lint repair/i)).not.toBeInTheDocument();
  });

  it.each([
    ["tests ran but zero tests were executed", testZeroCount, lintFailed, buildPassed],
    ["the baseline test validation failed", testFailed, lintFailed, buildPassed],
    ["no lint failure remains", testPassed, lintPassed, buildPassed],
    ["the baseline build failed", testPassed, lintFailed, buildFailed],
  ])("hides Accept documented baseline defects when %s", async (_case, testEvidence, lintEvidence, buildEvidence) => {
    vi.mocked(getBaselineValidation).mockImplementation((_runId: string, kind: string) => Promise.resolve(kind === "test" ? testEvidence : kind === "lint" ? lintEvidence : buildEvidence));
    renderPanel({ ...blockedAssessment, blockers: ["KNOWN_BASELINE_FAILURES_REQUIRE_POLICY"] });
    await waitFor(() => expect(getBaselineValidation).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Accept documented baseline defects" })).not.toBeInTheDocument();
  });

  it("hides Accept documented baseline defects while only pre-repair validation evidence exists", async () => {
    renderPanel(staleAssessment, [{ event_type: "REPAIR_APPLY_COMPLETED", sequence: 25 }]);
    await waitFor(() => expect(getBaselineValidation).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Accept documented baseline defects" })).not.toBeInTheDocument();
  });

  it("captures fresh parity, then qualifies under qualified_known_failures with explicit company policy", async () => {
    vi.mocked(getAuthoritativeRunState)
      .mockResolvedValueOnce(runState(21))
      .mockResolvedValueOnce(runState(22));
    renderPanel(staleAssessment, [{ event_type: "REPAIR_APPLY_COMPLETED", sequence: 15 }]);

    fireEvent.click(await screen.findByRole("button", { name: "Accept documented baseline defects" }));

    await waitFor(() => expect(qualifyBaseline).toHaveBeenCalled());
    expect(captureBaselineParity).toHaveBeenCalledWith("run-1", {
      expected_state_version: 21,
      idempotency_key: expect.stringMatching(/^accept-defects-run-1-\d+$/),
      actor: "control-tower",
    });
    expect(qualifyBaseline).toHaveBeenCalledWith("run-1", {
      expected_state_version: 22,
      idempotency_key: expect.stringMatching(/^qualify-known-run-1-\d+$/),
      actor: "control-tower",
      policy: "qualified_known_failures",
      company_policy_allows_known_failures: true,
    });
    expect(vi.mocked(captureBaselineParity).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(qualifyBaseline).mock.invocationCallOrder[0]);
  });

  it("refuses to qualify while parity still contains a test failure", async () => {
    vi.mocked(captureBaselineParity).mockResolvedValue(testFailureParity);
    renderPanel(staleAssessment, [{ event_type: "REPAIR_APPLY_COMPLETED", sequence: 15 }]);

    fireEvent.click(await screen.findByRole("button", { name: "Accept documented baseline defects" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("still contains a test failure");
    expect(qualifyBaseline).not.toHaveBeenCalled();
  });

  it("enables the existing human G03 approval after a zero-blocker qualified_with_known_failures package", async () => {
    vi.mocked(getAuthoritativeRunState)
      .mockResolvedValueOnce(runState(21))
      .mockResolvedValueOnce(runState(22));
    vi.mocked(decideG03).mockResolvedValue({ ...qualifiedWithKnownFailures, g03_decision: "approved", state_version: 31, event_sequence: 41 });
    renderPanel(staleAssessment, [{ event_type: "REPAIR_APPLY_COMPLETED", sequence: 15 }]);

    fireEvent.click(await screen.findByRole("button", { name: "Accept documented baseline defects" }));

    const approve = await screen.findByRole("button", { name: "Approve G03" });
    expect(approve).toBeEnabled();
    expect(decideG03).not.toHaveBeenCalledWith(expect.objectContaining({ decision: "approved" }));
    fireEvent.click(approve);

    await waitFor(() => expect(decideG03).toHaveBeenCalledWith("run-1", expect.objectContaining({ decision: "approved" })));
  });
});
