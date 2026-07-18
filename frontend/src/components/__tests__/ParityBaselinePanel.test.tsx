import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiClientError } from "@/api/client";
import { ParityBaselinePanel } from "@/components/ParityBaselinePanel";

const mocks = vi.hoisted(() => ({ getParityBaseline: vi.fn(), captureParityBaseline: vi.fn() }));
vi.mock("@/api/parityBaseline", () => mocks);
const evidence = { run_id: "run-1", evidence_id: "parity-1", status: "completed", payload: { routes: [{ path: "home" }], backend_integration: { api_roots: ["https://api.test"] }, sensitive_files: [{ file: "src/auth.ts", classification: "behavior_sensitive_requires_review", indicators: ["auth"], manual_review_required: true }], unknowns: ["DYNAMIC_OR_UNRESOLVED_ROUTES"] }, artifact_ids: ["artifact-1"], artifact_checksums: { "artifact-1": "sha256:one" }, prerequisite_artifact_ids: ["artifact-1"], error_code: null, state_version: 4, event_sequence: 8, idempotent_replay: false };

describe("ParityBaselinePanel", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.getParityBaseline.mockRejectedValue(new ApiClientError("missing", 404)); mocks.captureParityBaseline.mockResolvedValue(evidence); });
  it("renders empty state and submits authoritative inputs", async () => { render(<ParityBaselinePanel runId="run-1" stateVersion={4} connectionStatus="open" artifacts={[{ artifact_id: "artifact-1", checksum: "sha256:one" }]} />); fireEvent.click(await screen.findByRole("button", { name: "Inspect parity evidence" })); await waitFor(() => expect(mocks.captureParityBaseline).toHaveBeenCalledWith("run-1", expect.objectContaining({ expected_state_version: 4, prerequisite_artifact_ids: ["artifact-1"] }))); });
  it("renders structural evidence and stale feedback without local progression", async () => { mocks.getParityBaseline.mockRejectedValue(new ApiClientError("missing", 404)); mocks.captureParityBaseline.mockRejectedValue(new ApiClientError("stale", 409)); render(<ParityBaselinePanel runId="run-1" stateVersion={4} connectionStatus="open" artifacts={[{ artifact_id: "artifact-1", checksum: "sha256:one" }]} />); fireEvent.click(await screen.findByRole("button", { name: "Inspect parity evidence" })); expect(await screen.findByText(/The run changed/)).toBeInTheDocument(); });
});
