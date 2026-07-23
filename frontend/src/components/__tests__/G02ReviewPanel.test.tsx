import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { G02ReviewPanel } from "@/components/G02ReviewPanel";
import { decideG02, getG02Review } from "@/api/g02";
import type { G02ReviewResponse } from "@/types/generated/api";

vi.mock("@/api/g02", () => ({ getG02Review: vi.fn(), decideG02: vi.fn() }));

const state = { run_id: "run-1", status: "SOURCE_VALIDATED", run_phase: "PREFLIGHT_SNAPSHOT", phase_status: "running", approval_status: "pending", state_version: 4, preflight_id: "p1", source_path: "C:/source", target_output_path: "C:/target", graph_thread_id: "thread-1", created_at: "2026-01-01", updated_at: "2026-01-01", artifacts: [], workflow_events: [] } as never;
const review = { run_id: "run-1", gate_id: "G02", gate_version: "g02-v1", status: "pending", decision: null, package: { run_id: "run-1", gate_id: "G02", gate_version: "g02-v1", state_version: 4, actor: "operator", policy_version: "source-snapshot-policy-v1", snapshot_id: "snapshot-1", source_fingerprint: "sha256:source", snapshot_fingerprint: "sha256:snapshot", artifact_set_checksum: "sha256:artifacts", artifacts: [], integrity: { before_fingerprint: "sha256:source", after_snapshot_fingerprint: "sha256:source", snapshot_fingerprint: "sha256:snapshot", manifest_checksum: "manifest-1", policy_version: "source-snapshot-policy-v1", source_read_only_verified: true }, package_checksum: "sha256:package" }, baseline_input_boundary: null, state_version: 4, event_sequence: 6, idempotent_replay: false, stale_reason: null, comment: null } as unknown as G02ReviewResponse;

describe("G02ReviewPanel", () => {
  it("shows the blocked next step and records approval", async () => {
    vi.mocked(getG02Review).mockResolvedValue(review);
    vi.mocked(decideG02).mockResolvedValue({ ...(review as Record<string, unknown>), status: "approved", decision: "approved", baseline_input_boundary: "snapshot-1" } as never);
    render(<G02ReviewPanel runId="run-1" initialState={state} />);

    expect(await screen.findByText(/evidence is finalized and verified/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Record G02 decision" }));
    await waitFor(() => expect(decideG02).toHaveBeenCalledWith("run-1", expect.objectContaining({ expected_state_version: 4, decision: "approved" })));
    expect(await screen.findByText(/Baseline input boundary/)).toBeInTheDocument();
  });

  it("keeps the decision disabled while integrity evidence is not verified", async () => {
    vi.mocked(getG02Review).mockResolvedValue({ ...review, package: { ...review.package, integrity: { ...review.package.integrity, source_read_only_verified: false } } });
    render(<G02ReviewPanel runId="run-1" initialState={state} />);

    const button = await screen.findByRole("button", { name: "Record G02 decision" });
    expect(button).toBeDisabled();
    expect(screen.getByText(/blocked while source-integrity evidence is being finalized/)).toBeInTheDocument();
  });
});
