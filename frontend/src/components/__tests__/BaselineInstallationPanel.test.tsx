import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BaselineInstallationPanel } from "@/components/BaselineInstallationPanel";
import { cancelBaseline, getBaseline, getBaselineCommand, installBaseline } from "@/api/baseline";
import { getExecutionProfiles } from "@/api/executionProfiles";

vi.mock("@/api/baseline", () => ({ cancelBaseline: vi.fn(), getBaseline: vi.fn(), getBaselineCommand: vi.fn(), installBaseline: vi.fn() }));
vi.mock("@/api/executionProfiles", () => ({ getExecutionProfiles: vi.fn() }));

const state = { run_id: "run-1", status: "BASELINE_RUNNING", run_phase: "BASELINE", phase_status: "running", approval_status: "approved", repair_status: "not_required", state_version: 4, preflight_id: "p1", source_path: "C:/source", target_output_path: "C:/target", graph_thread_id: "thread", created_at: "2026-01-01", updated_at: "2026-01-01", artifacts: [], workflow_events: [] } as never;
const baseline = { run_id: "run-1", status: "qualified", blockers: [], authorization_status: "authorized" } as never;
const profile = { run_id: "run-1", status: "selected", selected_profile: { profile_id: "profile-1", checksum: "sha256:runtime" }, blockers: [] } as never;
const result = { run_id: "run-1", execution_id: "execution-1", command_id: "npm-ci-bootstrap", status: "RUNNING", exit_code: null, started_at: "2026-01-01", finished_at: null, duration_ms: null, timed_out: false, cancelled: false, reconstruction_required: false, runtime_checksum: "sha256:runtime", baseline_checksum: "sha256:baseline", blockers: [], artifact_ids: [], state_version: 6, event_sequence: 6, idempotent_replay: false } as never;

async function startWith(installation: typeof result, refreshAuthoritativeState = vi.fn()) {
  vi.mocked(getBaseline).mockResolvedValue(baseline);
  vi.mocked(getExecutionProfiles).mockResolvedValue(profile);
  vi.mocked(installBaseline).mockResolvedValue(installation);
  render(<BaselineInstallationPanel runId="run-1" initialState={state} connectionStatus="open" refreshAuthoritativeState={refreshAuthoritativeState} />);
  fireEvent.click(await screen.findByRole("button", { name: "Install frozen baseline" }));
  await waitFor(() => expect(installBaseline).toHaveBeenCalled());
  return refreshAuthoritativeState;
}

describe("BaselineInstallationPanel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("starts the frozen command with the selected checksum and renders running state", async () => {
    const refreshAuthoritativeState = await startWith(result);
    await waitFor(() => expect(installBaseline).toHaveBeenCalledWith("run-1", expect.objectContaining({ expected_state_version: 4, runtime_profile_id: "profile-1", runtime_checksum: "sha256:runtime" })));
    expect(await screen.findByText("running")).toBeInTheDocument();
    expect(screen.getByText("Live installation events")).toBeInTheDocument();
    expect(refreshAuthoritativeState).toHaveBeenCalledTimes(1);
  });

  it("fails closed when the runtime profile is blocked", async () => {
    vi.mocked(getBaseline).mockResolvedValue(baseline);
    vi.mocked(getExecutionProfiles).mockResolvedValue({ ...(profile as Record<string, unknown>), status: "blocked", selected_profile: null } as never);
    render(<BaselineInstallationPanel runId="run-1" initialState={state} connectionStatus="reconnecting" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No compatible approved runtime profile");
    expect(screen.getByRole("button", { name: "Install frozen baseline" })).toBeDisabled();
    expect(screen.getByText("Connection lost. Reconnecting...")).toBeInTheDocument();
  });

  it("can cancel a running installation", async () => {
    vi.mocked(getBaseline).mockResolvedValue(baseline);
    vi.mocked(getExecutionProfiles).mockResolvedValue(profile);
    vi.mocked(installBaseline).mockResolvedValue(result);
    vi.mocked(cancelBaseline).mockResolvedValue({ ...(result as Record<string, unknown>), status: "CANCELLED", cancelled: true } as never);
    vi.mocked(getBaselineCommand).mockResolvedValue({ ...(result as Record<string, unknown>), status: "CANCELLED", cancelled: true } as never);
    render(<BaselineInstallationPanel runId="run-1" initialState={state} connectionStatus="open" />);
    fireEvent.click(await screen.findByRole("button", { name: "Install frozen baseline" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel installation" }));
    await waitFor(() => expect(cancelBaseline).toHaveBeenCalledWith("run-1", "execution-1", expect.objectContaining({ actor: "control-tower" })));
    expect(await screen.findByText("cancelled")).toBeInTheDocument();
  });

  it("projects authoritative output chunks into the live log viewer", async () => {
    vi.mocked(getBaseline).mockResolvedValue(baseline);
    vi.mocked(getExecutionProfiles).mockResolvedValue(profile);
    vi.mocked(installBaseline).mockResolvedValue(result);
    const outputState = { ...(state as Record<string, unknown>), workflow_events: [{ event_id: "event-output", run_id: "run-1", stage_id: null, event_type: "COMMAND_OUTPUT_CHUNK", occurred_at: "2026-01-01T00:00:00Z", sequence: 5, payload: { execution_id: "execution-1", stream: "stdout", chunk: "npm ci started\\n" } }] } as never;
    render(<BaselineInstallationPanel runId="run-1" initialState={outputState} connectionStatus="open" />);
    fireEvent.click(await screen.findByRole("button", { name: "Install frozen baseline" }));
    expect(await screen.findByLabelText("Baseline installation live logs")).toHaveTextContent("npm ci started");
  });

  it("tolerates undefined blockers", async () => {
    await startWith({ ...(result as Record<string, unknown>), blockers: undefined } as never);
    expect(await screen.findByText("running")).toBeInTheDocument();
    expect(screen.queryByText(/Failure class:/)).not.toBeInTheDocument();
  });

  it("tolerates null blockers", async () => {
    await startWith({ ...(result as Record<string, unknown>), blockers: null } as never);
    expect(await screen.findByText("running")).toBeInTheDocument();
    expect(screen.queryByText(/Failure class:/)).not.toBeInTheDocument();
  });

  it("renders empty blockers without failure details", async () => {
    await startWith({ ...(result as Record<string, unknown>), blockers: [] } as never);
    expect(await screen.findByText("running")).toBeInTheDocument();
    expect(screen.queryByText(/Failure class:/)).not.toBeInTheDocument();
  });

  it("preserves populated blocker details", async () => {
    await startWith({ ...(result as Record<string, unknown>), status: "FAILED", blockers: ["ENVIRONMENT_REGISTRY_UNAVAILABLE"] } as never);
    expect(await screen.findByText("Failure class: environment")).toBeInTheDocument();
    expect(screen.getByText("ENVIRONMENT_REGISTRY_UNAVAILABLE")).toBeInTheDocument();
  });

  it("renders a partial installation projection without crashing", async () => {
    await startWith({ ...(result as Record<string, unknown>), blockers: undefined, artifact_ids: undefined, started_at: undefined, duration_ms: undefined } as never);
    expect(await screen.findByText("running")).toBeInTheDocument();
    expect(screen.getByLabelText("Baseline installation live logs")).toBeInTheDocument();
    expect(screen.queryByText(/projection incomplete/i)).not.toBeInTheDocument();
  });

  it("renders required-field corruption as a stable diagnostic", async () => {
    await startWith({ ...(result as Record<string, unknown>), command_id: undefined } as never);
    expect(await screen.findByRole("alert", { name: "" })).toHaveTextContent("Installation projection incomplete");
    expect(screen.getByRole("alert", { name: "" })).toHaveTextContent("command_id");
    expect(screen.getByRole("heading", { name: "Frozen baseline clean installation" })).toBeInTheDocument();
  });

  it("renders an existing installation success state", async () => {
    await startWith({ ...(result as Record<string, unknown>), status: "SUCCEEDED", exit_code: 0, duration_ms: 1200 } as never);
    expect(await screen.findByText("succeeded")).toBeInTheDocument();
    expect(screen.getByText("1200 ms")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel installation" })).not.toBeInTheDocument();
  });

  it("renders an existing installation failure state", async () => {
    await startWith({ ...(result as Record<string, unknown>), status: "FAILED", exit_code: 1, blockers: ["PROJECT_INSTALL_FAILED"] } as never);
    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(screen.getByText("PROJECT_INSTALL_FAILED")).toBeInTheDocument();
    expect(screen.getByText("Failure class: project or workspace")).toBeInTheDocument();
  });

  it("keeps Transformer commands out of the baseline installation projection", async () => {
    vi.useFakeTimers();
    vi.mocked(getBaseline).mockResolvedValue(baseline);
    vi.mocked(getExecutionProfiles).mockResolvedValue(profile);
    vi.mocked(getBaselineCommand).mockResolvedValue({ ...(result as Record<string, unknown>), status: "SUCCEEDED" } as never);
    const events = [
      { event_id: "baseline", run_id: "run-1", stage_id: null, event_type: "COMMAND_STARTED", occurred_at: "2026-01-01", sequence: 1, payload: { execution_id: "execution-baseline" } },
      { event_id: "transformer", run_id: "run-1", stage_id: "angular-18-to-19", event_type: "COMMAND_STARTED", occurred_at: "2026-01-02", sequence: 2, payload: { execution_id: "execution-transformer" } },
    ];
    render(<BaselineInstallationPanel runId="run-1" initialState={{ ...(state as Record<string, unknown>), workflow_events: events } as never} connectionStatus="open" />);
    await act(async () => {
      await Promise.resolve();
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
    });
    expect(getBaselineCommand).toHaveBeenCalledWith("run-1", "execution-baseline");
    expect(getBaselineCommand).not.toHaveBeenCalledWith("run-1", "execution-transformer");
    vi.useRealTimers();
  });

  it("normalizes defaulted arrays at the baseline API boundary", async () => {
    const actual = await vi.importActual<typeof import("@/api/baseline")>("@/api/baseline");
    const client = { get: vi.fn().mockResolvedValue({ ...(result as Record<string, unknown>), blockers: null, artifact_ids: undefined }) };
    const normalized = await actual.getBaselineCommand("run-1", "execution-1", client as never);
    expect(normalized.blockers).toEqual([]);
    expect(normalized.artifact_ids).toEqual([]);
  });
});
