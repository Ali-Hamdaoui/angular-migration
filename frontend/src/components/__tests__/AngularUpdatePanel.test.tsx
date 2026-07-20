import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AngularUpdatePanel } from "../AngularUpdatePanel";

vi.mock("@/api/transformations", () => ({
  getAngularUpdate: vi.fn(),
  getTargetVersionTyped: vi.fn(),
  startAngularUpdate: vi.fn(),
  verifyTargetVersion: vi.fn(),
}));

import {
  getAngularUpdate,
  getTargetVersionTyped,
  startAngularUpdate,
  verifyTargetVersion,
} from "@/api/transformations";

function mockGetAngularUpdate(status: string, overrides: Record<string, unknown> = {}) {
  (getAngularUpdate as ReturnType<typeof vi.fn>).mockResolvedValue({
    run_id: "run-1",
    stage_id: "stage-1",
    status,
    target_version_status: null,
    resolved_target_version: null,
    command_execution_id: null,
    artifact_ids: [],
    state_version: 1,
    event_sequence: 1,
    ...overrides,
  });
}

function mockGetTargetVersionTyped(overrides: Record<string, unknown> = {}) {
  (getTargetVersionTyped as ReturnType<typeof vi.fn>).mockResolvedValue({
    run_id: "run-1",
    stage_id: "stage-1",
    target_version_status: "verified",
    resolved_target_version: "18.2.0",
    evidence_sources: { "package.json": "18.2.0", "ng version": "18.2.0" },
    all_sources_agree: true,
    disagreements: [],
    artifact_ids: [],
    ...overrides,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AngularUpdatePanel", () => {
  it("renders loading skeleton with correct a11y", () => {
    (getAngularUpdate as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(screen.getByText("Angular Update")).toBeTruthy();
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("renders empty state with Start button", async () => {
    mockGetAngularUpdate("pending");
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(await screen.findByText("Start Angular Update")).toBeTruthy();
    expect(screen.getByText("17.0.0")).toBeTruthy();
    expect(screen.getByText("18.0.0")).toBeTruthy();
  });

  it("renders running state with status pill", async () => {
    mockGetAngularUpdate("running");
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(await screen.findByText("RUNNING")).toBeTruthy();
  });

  it("renders success state and fetches target version", async () => {
    mockGetAngularUpdate("succeeded", { target_version_status: "verified", resolved_target_version: "18.2.0" });
    mockGetTargetVersionTyped();
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(await screen.findByText("Verify Target Version")).toBeTruthy();
    await vi.waitFor(() => {
      expect(screen.getByText("Yes ✓")).toBeTruthy();
    });
  });

  it("renders failure state with error message", async () => {
    mockGetAngularUpdate("failed", { error_message: "Something went wrong" });
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(await screen.findByText("Something went wrong")).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("renders blocked state for interactive prompt", async () => {
    mockGetAngularUpdate("interactive_blocked");
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(await screen.findByText("Interactive prompt detected. Manual intervention required.")).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("renders no_evidence state when fetch returns null", async () => {
    (getAngularUpdate as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Not found"));
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(await screen.findByText("No Angular update evidence found for this stage.")).toBeTruthy();
  });

  it("transitions to success via SSE ANGULAR_UPDATE_COMPLETED", async () => {
    (getAngularUpdate as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    const onStateChange = vi.fn();
    const { rerender } = render(
      <AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} onStateChange={onStateChange} />
    );
    expect(screen.getByText("Angular Update")).toBeTruthy();
    const sseEvents = [
      {
        id: "evt-1",
        event_type: "ANGULAR_UPDATE_COMPLETED",
        payload: { target_version_status: "verified", state_version: 2 },
      },
    ];
    rerender(
      <AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} onStateChange={onStateChange} workflowEvents={sseEvents} />
    );
    expect(await screen.findByText("PASSED")).toBeTruthy();
    expect(onStateChange).toHaveBeenCalledWith(2);
  });

  it("transitions to failure via SSE ANGULAR_UPDATE_FAILED", async () => {
    (getAngularUpdate as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(
      <AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} workflowEvents={[
        { id: "evt-2", event_type: "ANGULAR_UPDATE_FAILED", payload: { error_message: "Command failed" } },
      ]} />
    );
    expect(await screen.findByText("Command failed")).toBeTruthy();
  });

  it("transitions to blocked via SSE INTERACTIVE_DECISION_REQUIRED", async () => {
    (getAngularUpdate as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(
      <AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} workflowEvents={[
        { id: "evt-3", event_type: "INTERACTIVE_DECISION_REQUIRED", payload: {} },
      ]} />
    );
    expect(await screen.findByText("Interactive prompt detected. Manual intervention required.")).toBeTruthy();
  });

  it("prevents duplicate start update click", async () => {
    mockGetAngularUpdate("pending");
    (startAngularUpdate as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    const btn = await screen.findByRole("button", { name: "Start Angular Update" });
    fireEvent.click(btn);
    await vi.waitFor(() => {
      expect(screen.queryByRole("button", { name: "Start Angular Update" })).toBeFalsy();
    });
  });

  it("shows mismatch state via SSE", async () => {
    (getAngularUpdate as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(
      <AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} workflowEvents={[
        { id: "evt-4", event_type: "ANGULAR_UPDATE_COMPLETED", payload: { target_version_status: "mismatch", state_version: 3 } },
      ]} />
    );
    expect(await screen.findByText("Target version mismatch")).toBeTruthy();
  });

  it("handles cancelled state", async () => {
    (getAngularUpdate as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(
      <AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} workflowEvents={[
        { id: "evt-5", event_type: "ANGULAR_UPDATE_FAILED", payload: { error_message: "Cancelled by operator" } },
      ]} />
    );
    expect(await screen.findByText("Angular update was cancelled")).toBeTruthy();
  });

  it("has correct a11y attributes", async () => {
    (getAngularUpdate as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(screen.getByRole("region", { name: "Angular Update" })).toBeTruthy();
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("shows execution ID when available", async () => {
    mockGetAngularUpdate("running", { command_execution_id: "exec-abc-123" });
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(await screen.findByText("exec-abc-123")).toBeTruthy();
    expect(screen.getByText("Execution ID")).toBeTruthy();
  });

  it("shows artifact count when available", async () => {
    mockGetAngularUpdate("running", { artifact_ids: ["art-1", "art-2"] });
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    expect(await screen.findByText("2")).toBeTruthy();
    expect(screen.getByText("Artifacts")).toBeTruthy();
  });

  it("shows disagreement in target verification", async () => {
    mockGetAngularUpdate("succeeded", { target_version_status: "verified", resolved_target_version: "18.2.0" });
    mockGetTargetVersionTyped({
      all_sources_agree: false,
      disagreements: ["package.json says 18.2.0, ng version says 18.0.0"],
    });
    render(<AngularUpdatePanel runId="r1" stageId="s1" sourceVersion="17.0.0" targetVersion="18.0.0" expectedStateVersion={1} />);
    await vi.waitFor(() => {
      expect(screen.getByText("No ✗")).toBeTruthy();
    });
  });
});
