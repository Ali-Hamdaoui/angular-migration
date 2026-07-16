import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("BaselineInstallationPanel", () => {
  it("starts the frozen command with the selected checksum and renders running state", async () => {
    vi.mocked(getBaseline).mockResolvedValue(baseline);
    vi.mocked(getExecutionProfiles).mockResolvedValue(profile);
    vi.mocked(installBaseline).mockResolvedValue(result);
    render(<BaselineInstallationPanel runId="run-1" initialState={state} connectionStatus="open" />);
    fireEvent.click(await screen.findByRole("button", { name: "Install frozen baseline" }));
    await waitFor(() => expect(installBaseline).toHaveBeenCalledWith("run-1", expect.objectContaining({ expected_state_version: 4, runtime_profile_id: "profile-1", runtime_checksum: "sha256:runtime" })));
    expect(await screen.findByText("running")).toBeInTheDocument();
    expect(screen.getByText("Live installation events")).toBeInTheDocument();
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
});
