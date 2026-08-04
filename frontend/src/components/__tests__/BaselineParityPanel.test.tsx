import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BaselineParityPanel } from "@/components/BaselineParityPanel";
import { ApiClientError } from "@/api/client";

const mocks = vi.hoisted(() => ({ getBaselineParitySection: vi.fn(), captureBaselineParity: vi.fn() }));
const { getBaselineParitySection, captureBaselineParity } = mocks;
vi.mock("@/api/baselineParity", () => mocks);

const evidence = {
  run_id: "run-1", evidence_id: "parity-1", status: "captured", schema_version: "baseline-parity-v1", parser_version: "baseline-parsers-v1", baseline_checksum: "sha256:baseline", runtime_profile_id: "profile-1", runtime_checksum: "sha256:runtime",
  failures: [{ fingerprint: "sha256:failure", group: "test:failure", kind: "test", message: "expected 1", origin: "pre-existing", severity: "error", count: 1, confidence: "machine_proven", parser_version: "baseline-parsers-v1", schema_version: "baseline-parity-v1" }],
  routes: [{ path: "home", file: "src/app.routes.ts" }], backend_integration: { api_roots: ["https://api.example.test"] }, anchors: [], confidence: { failures: "machine_proven", routes: "machine_proven", backend_integration: "machine_proven", anchors: "machine_proven" }, source_artifact_ids: [], artifact_ids: ["artifact-1"], artifact_checksums: { "artifact-1": "sha256:artifact" }, state_version: 4, event_sequence: 7, idempotent_replay: false,
};

describe("BaselineParityPanel", () => {
  beforeEach(() => { vi.clearAllMocks(); getBaselineParitySection.mockRejectedValue(new ApiClientError("missing", 404)); captureBaselineParity.mockResolvedValue(evidence); });

  it("shows an empty state and captures evidence", async () => {
    render(<BaselineParityPanel runId="run-1" stateVersion={1} connectionStatus="open" workflowEvents={[{ event_type: "BASELINE_BUILD_COMPLETED" }, { event_type: "BASELINE_TESTS_COMPLETED" }, { event_type: "BASELINE_LINT_COMPLETED" }]} />);
    expect(await screen.findByText("No parity evidence has been captured.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Capture baseline parity" }));
    await waitFor(() => { expect(captureBaselineParity).toHaveBeenCalled(); });
  });

  it("renders confidence, pre-existing failures, and evidence tabs", async () => {
    getBaselineParitySection.mockResolvedValue(evidence);
    render(<BaselineParityPanel runId="run-1" stateVersion={4} connectionStatus="reconnecting" />);
    expect(await screen.findByText("expected 1")).toBeInTheDocument();
    expect(screen.getByText("pre-existing")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Routes" }));
    expect(screen.getByText(/home/)).toBeInTheDocument();
    expect(screen.getByText(/Connection lost/)).toBeInTheDocument();
  });

  it("shows stale capture feedback and does not render sensitive integration contents", async () => {
    getBaselineParitySection.mockResolvedValue({ ...evidence, backend_integration: { api_roots: ["https://example.test/api"], authentication_file_references: ["src/auth.interceptor.ts"] } });
    captureBaselineParity.mockRejectedValue(new ApiClientError("stale", 409));
    render(<BaselineParityPanel runId="run-1" stateVersion={4} connectionStatus="open" />);
    await screen.findByText("expected 1");
    fireEvent.click(screen.getByRole("button", { name: "Backend integration" }));
    expect(screen.queryByText("super-secret-token")).not.toBeInTheDocument();
  });

  it("shows an integrity warning when G03 exists without baseline reference evidence", async () => {
    render(<BaselineParityPanel runId="run-1" stateVersion={9} connectionStatus="open" workflowEvents={[{ event_type: "G03_CREATED" }]} />);
    expect(await screen.findByText("Required baseline reference evidence is missing. The current G03 package is not valid for approval.")).toBeInTheDocument();
    expect(screen.getByText("integrity error")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Capture baseline parity" })).not.toBeInTheDocument();
  });

  it("renders a valid empty capture as captured", async () => {
    getBaselineParitySection.mockResolvedValue({ ...evidence, failures: [], routes: [], backend_integration: {}, anchors: [] });
    render(<BaselineParityPanel runId="run-1" stateVersion={4} connectionStatus="open" />);
    expect(await screen.findByText("captured")).toBeInTheDocument();
    expect(screen.getByText("No pre-existing baseline failures were fingerprinted.")).toBeInTheDocument();
    expect(screen.queryByText("not captured")).not.toBeInTheDocument();
  });
});
