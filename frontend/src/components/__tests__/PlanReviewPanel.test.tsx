import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PlanReviewPanel } from "@/components/PlanReviewPanel";
import { usePlanReview } from "@/hooks/usePlanReview";
import { decideG06, getPlanReview } from "@/api/planningReview";
import { ApiClientError } from "@/api/client";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

vi.mock("@/hooks/usePlanReview", () => ({ usePlanReview: vi.fn() }));
vi.mock("@/api/planningReview", () => ({ getPlanReview: vi.fn(), decideG06: vi.fn(), explainPlan: vi.fn(), revisePlan: vi.fn() }));

const checksum = "sha256:" + "a".repeat(64);
const state = { run_id: "run-1", state_version: 4, workflow_events: [] } as unknown as AuthoritativeRunStateDto;
const review = {
  run_id: "run-1", status: "pending", plan: { version: 1 }, stage_plan: { stage_id: "stage-1" }, plan_checksum: checksum, stage_plan_checksum: checksum,
  diff: { from_version: 1, to_version: 2, changed_fields: ["builder"], changes: { builder: "approved" }, checksum }, package: { artifact_set_checksum: checksum, package_checksum: checksum, narrative: { summary: "Advisory explanation", rationale: ["Exact versions are retained."], risks: [] } }, artifact_ids: ["artifact-1"], artifact_checksums: { "artifact-1": checksum }, artifact_links: {}, gate_id: "G06", gate_version: "g06-v1", gate_status: "pending", gate_decision: null, package_checksum: checksum, state_version: 4, event_sequence: 8, idempotent_replay: false,
};
const baseResult = { review, status: "success" as const, error: null, lastAction: null, refresh: vi.fn(), revise: vi.fn(), explain: vi.fn(), decide: vi.fn() };

describe("PlanReviewPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(usePlanReview).mockReturnValue(baseResult);
  });

  it("renders subordinate headings when embedded in a pipeline stage", () => {
    render(<PlanReviewPanel runId="run-1" initialState={state} connectionStatus="open" refreshAuthoritativeState={vi.fn()} headingLevel={4} />);
    expect(screen.getByRole("heading", { name: "Review and approve MigrationPlan", level: 4 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "G06 decision", level: 5 })).toBeInTheDocument();
  });

  it("renders immutable diff, separated explanation, evidence, and accessible G06 controls", () => {
    render(<PlanReviewPanel runId="run-1" initialState={state} connectionStatus="open" refreshAuthoritativeState={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Review and approve MigrationPlan" })).toBeInTheDocument();
    expect(screen.getByLabelText("Plan version")).toBeInTheDocument();
    expect(screen.getByText("Immutable version diff")).toBeInTheDocument();
    expect(screen.getByText("Advisory explanation")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "artifact-1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve G06" })).toBeEnabled();
  });

  it.each([
    ["undefined", undefined],
    ["null", null],
    ["empty", []],
  ])("renders the empty evidence state when artifact_ids is %s", (_label, artifactIds) => {
    vi.mocked(usePlanReview).mockReturnValue({ ...baseResult, review: { ...review, artifact_ids: artifactIds } } as never);
    render(<PlanReviewPanel runId="run-1" initialState={state} connectionStatus="open" refreshAuthoritativeState={vi.fn()} />);
    expect(screen.getByText("No reviewer artifacts are available.")).toBeInTheDocument();
    expect(within(screen.getByRole("heading", { name: "Registered evidence" }).parentElement!).queryByRole("list")).not.toBeInTheDocument();
  });

  it("keeps G06 actions disabled when the evidence package is unavailable", () => {
    vi.mocked(usePlanReview).mockReturnValue({ ...baseResult, review: { ...review, package_checksum: null } });
    render(<PlanReviewPanel runId="run-1" initialState={state} connectionStatus="open" refreshAuthoritativeState={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Approve G06" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Request modification" })).toBeDisabled();
  });

  it("exposes stale and backend failure states without advancing workflow locally", () => {
    vi.mocked(usePlanReview).mockReturnValue({ ...baseResult, status: "stale", error: "Plan review failed. Correlation ID: corr-1" });
    render(<PlanReviewPanel runId="run-1" initialState={state} connectionStatus="open" refreshAuthoritativeState={vi.fn()} />);
    expect(screen.getAllByRole("alert").map((alert) => alert.textContent).join(" ")).toContain("stale");
    expect(screen.getAllByRole("alert").map((alert) => alert.textContent).join(" ")).toContain("corr-1");
  });

  it("passes the reviewer decision to the checksum-bound G06 hook without local advancement", () => {
    const decide = vi.fn().mockResolvedValue(null);
    vi.mocked(usePlanReview).mockReturnValue({ ...baseResult, decide });
    render(<PlanReviewPanel runId="run-1" initialState={state} connectionStatus="open" refreshAuthoritativeState={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Keep the exact execution contract" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve G06" }));

    expect(decide).toHaveBeenCalledWith("approve", "Keep the exact execution contract");
    expect(screen.getByText("pending")).toBeInTheDocument();
  });

  it("keeps every G06 API binding and reloads authoritative state after a 409", async () => {
    const { usePlanReview: useActualPlanReview } = await vi.importActual<typeof import("@/hooks/usePlanReview")>("@/hooks/usePlanReview");
    const refreshAuthoritativeState = vi.fn().mockResolvedValue(undefined);
    vi.mocked(getPlanReview).mockResolvedValue(review as never);
    vi.mocked(decideG06).mockRejectedValue(new ApiClientError("stale", 409));

    function HookHarness() {
      const result = useActualPlanReview({
        runId: "run-1",
        stateVersion: 4,
        workflowEvents: [{ event_type: "G06_CREATED", sequence: 8 }],
        connectionStatus: "open",
        refreshAuthoritativeState,
      });
      return <>
        <p>{result.review?.gate_status ?? "loading"}</p>
        <button type="button" disabled={!result.review || result.status === "running"} onClick={() => void result.decide("approve_with_comment", "Preserve the G06 draft")}>Submit bound G06 decision</button>
      </>;
    }

    render(<HookHarness />);
    fireEvent.click(await screen.findByRole("button", { name: "Submit bound G06 decision" }));

    await vi.waitFor(() => expect(decideG06).toHaveBeenCalledWith("run-1", {
      expected_state_version: 4,
      idempotency_key: expect.stringMatching(/^planning-review-g06-run-1-/),
      gate_version: "g06-v1",
      package_checksum: checksum,
      artifact_set_checksum: checksum,
      plan_checksum: checksum,
      stage_plan_checksum: checksum,
      decision: "approve_with_comment",
      comment: "Preserve the G06 draft",
      correlation_id: expect.any(String),
    }));
    await vi.waitFor(() => expect(refreshAuthoritativeState).toHaveBeenCalled());
    expect(screen.getByText("pending")).toBeInTheDocument();
  });
});
