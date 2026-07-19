import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StageTestPanel } from "@/components/StageTestPanel";
import { ApiClientError } from "@/api/client";
import { getStageTests, startStageTests } from "@/api/stageTests";

vi.mock("@/api/stageTests", () => ({
  cancelStageTests: vi.fn(),
  getStageTests: vi.fn(),
  getStageTestLogs: vi.fn(),
  startStageTests: vi.fn(),
}));

const response = {
  test_id: "test-1",
  run_id: "run-1",
  stage_id: "stage-1",
  status: "passed_with_manual_items",
  suites: [
    { suite_id: "suite-1", name: "Unit tests", kind: "unit", mandatory: true, status: "passed", test_count: 42, passed: 40, failed: 2, skipped: 0, duration_ms: 30000, warnings: ["slow test"], failed_tests: ["Header renders"], artifact_ids: ["artifact-1"], is_baseline: true },
    { suite_id: "suite-2", name: "Lint", kind: "lint", mandatory: false, status: "not_configured", test_count: null, passed: null, failed: null, skipped: null, duration_ms: null, warnings: [], failed_tests: [], artifact_ids: [], is_baseline: false },
  ],
  changes: [
    { test_id: "change-1", name: "Header renders", suite_name: "Unit tests", kind: "unit", group: "new", previous_status: null, current_status: "failed", previous_duration_ms: null, current_duration_ms: 500 },
  ],
  logs: ["test output"],
  artifact_ids: ["artifact-1"],
  artifact_checksums: { "artifact-1": "sha256:test-out" },
  state_version: 2,
  event_sequence: 3,
  idempotent_replay: false,
};

describe("StageTestPanel", () => {
  it("shows loading state initially", () => {
    vi.mocked(getStageTests).mockReturnValue(new Promise(() => {}));
    render(<StageTestPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(screen.getByText("Loading stage test state...")).toBeInTheDocument();
  });

  it("renders test suites with baseline/new/resolved grouping", async () => {
    vi.mocked(getStageTests).mockResolvedValue(response);
    render(<StageTestPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    const unitTests = await screen.findAllByText(/Unit tests/);
    expect(unitTests.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("not configured")).toBeInTheDocument();
    const headerRenders = await screen.findAllByText("Header renders");
    expect(headerRenders.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("Live test suite state")).toBeInTheDocument();
  });

  it("shows empty state when no tests exist", async () => {
    vi.mocked(getStageTests).mockRejectedValue(new ApiClientError("not found", 404));
    render(<StageTestPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("No stage tests have been started yet.")).toBeInTheDocument();
  });

  it("shows error state on backend failure", async () => {
    vi.mocked(getStageTests).mockRejectedValue(new ApiClientError("server error", 500));
    render(<StageTestPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("Stage test evidence could not be loaded.")).toBeInTheDocument();
  });
});
