import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PlanReviewPanel } from "@/components/PlanReviewPanel";
import { usePlanReview } from "@/hooks/usePlanReview";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

vi.mock("@/hooks/usePlanReview", () => ({ usePlanReview: vi.fn() }));

const checksum = "sha256:" + "a".repeat(64);
const state = { run_id: "run-1", state_version: 4, workflow_events: [] } as unknown as AuthoritativeRunStateDto;
const review = {
  run_id: "run-1", status: "pending", plan: { version: 1 }, stage_plan: { stage_id: "stage-1" }, plan_checksum: checksum, stage_plan_checksum: checksum,
  diff: { from_version: 1, to_version: 2, changed_fields: ["builder"], changes: { builder: "approved" }, checksum }, package: { artifact_set_checksum: checksum, package_checksum: checksum, narrative: { summary: "Advisory explanation", rationale: ["Exact versions are retained."], risks: [] } }, artifact_ids: ["artifact-1"], artifact_checksums: { "artifact-1": checksum }, artifact_links: {}, gate_id: "G06", gate_version: "g06-v1", gate_status: "pending", gate_decision: null, package_checksum: checksum, state_version: 4, event_sequence: 8, idempotent_replay: false,
};
const baseResult = { review, status: "success" as const, error: null, lastAction: null, refresh: vi.fn(), revise: vi.fn(), explain: vi.fn(), decide: vi.fn() };

describe("PlanReviewPanel", () => {
  beforeEach(() => vi.mocked(usePlanReview).mockReturnValue(baseResult));

  it("renders immutable diff, separated explanation, evidence, and accessible G06 controls", () => {
    render(<PlanReviewPanel runId="run-1" initialState={state} connectionStatus="open" refreshAuthoritativeState={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Review and approve MigrationPlan" })).toBeInTheDocument();
    expect(screen.getByLabelText("Plan version")).toBeInTheDocument();
    expect(screen.getByText("Immutable version diff")).toBeInTheDocument();
    expect(screen.getByText("Advisory explanation")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "artifact-1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve G06" })).toBeEnabled();
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
});
