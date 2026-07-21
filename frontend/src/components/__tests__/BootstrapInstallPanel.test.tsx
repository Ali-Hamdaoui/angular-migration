import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { BootstrapInstallPanel } from "@/components/BootstrapInstallPanel";
import { getBootstrapInstallStatus, runBootstrapInstall } from "@/api/stages";

vi.mock("@/api/stages", () => ({
  getBootstrapInstallStatus: vi.fn(),
  runBootstrapInstall: vi.fn(),
}));

const runId = "run-001";
const stageId = "stage-001";

function makeStatus(overrides: Record<string, unknown> = {}) {
  return {
    run_id: runId,
    stage_id: stageId,
    step_id: "step-001",
    name: "bootstrap_install",
    status: "not_started",
    command: "npm ci",
    exit_code: null,
    started_at: null,
    completed_at: null,
    state_version: 5,
    event_sequence: 3,
    artifact_ids: [],
    runtime_profile: null,
    stage_sandbox: null,
    g07_status: null,
    lifecycle_script_audit_ref: null,
    pre_fingerprint: null,
    post_fingerprint: null,
    failure_classification: null,
    blocker_code: null,
    retry_eligible: false,
    recovery_required: false,
    reconstruction_guidance: null,
    correlation_id: null,
    ...overrides,
  };
}

function makeInstallResponse(overrides: Record<string, unknown> = {}) {
  return {
    ...makeStatus(overrides),
    idempotent_replay: false,
  };
}

describe("BootstrapInstallPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(getBootstrapInstallStatus).mockRejectedValue(new ApiClientError("not found", 404, "GET", "/status"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows loading state then not found state", async () => {
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    expect(screen.getByText(/Loading bootstrap install status/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/No bootstrap installation has been started/)).toBeInTheDocument());
  });

  it("shows ready state with start button", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({ status: "not_started" }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} runStateVersion={5} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Start bootstrap install" })).toBeInTheDocument());
  });

  it("shows starting state", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({ status: "not_started" }));
    vi.mocked(runBootstrapInstall).mockImplementation(() => new Promise(() => {}));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} runStateVersion={5} />);
    await waitFor(() => screen.getByRole("button", { name: "Start bootstrap install" }));
    fireEvent.click(screen.getByRole("button", { name: "Start bootstrap install" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled());
  });

  it("shows running state", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "RUNNING", started_at: "2026-07-21T12:00:00Z",
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByText("Running…")).toBeInTheDocument());
  });

  it("shows completed state with exit code and duration", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "COMPLETED", exit_code: 0,
      started_at: "2026-07-21T12:00:00Z", completed_at: "2026-07-21T12:00:30Z",
      g07_status: "approved",
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByText(/completed successfully/)).toBeInTheDocument());
    expect(screen.getByText("0").closest("dd")).toBeInTheDocument();
    expect(screen.getByText("30s")).toBeInTheDocument();
  });

  it("shows failed state with retry button when retry eligible", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "FAILED", exit_code: 1, retry_eligible: true, recovery_required: false,
      failure_classification: "UNKNOWN_COMMAND_FAILURE",
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry bootstrap install" })).toBeInTheDocument());
  });

  it("shows failed state without retry when not retry eligible", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "FAILED", exit_code: 1, retry_eligible: false, recovery_required: false,
      failure_classification: "UNSAFE_COMMAND",
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByText(/Retry is not authorized/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("shows cancelled state", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "CANCELLED", exit_code: null, recovery_required: false,
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByText("cancelled")).toBeInTheDocument());
  });

  it("shows interrupted state", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "INTERRUPTED", exit_code: null, recovery_required: true,
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByText("interrupted")).toBeInTheDocument());
  });

  it("shows recovery required guidance", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "RECOVERY_REQUIRED", recovery_required: true,
      reconstruction_guidance: "Reconstruct the authoritative stage sandbox before retrying.",
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByText(/Reconstruct the authoritative/)).toBeInTheDocument());
  });

  it("shows stale G07 warning", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "COMPLETED", g07_status: "missing",
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByText(/G07 authorization record is missing/)).toBeInTheDocument());
  });

  it("starts install with stable idempotency key", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({ status: "not_started" }));
    vi.mocked(runBootstrapInstall).mockResolvedValue(makeInstallResponse({ status: "COMPLETED" }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} runStateVersion={5} />);
    await waitFor(() => screen.getByRole("button", { name: "Start bootstrap install" }));
    fireEvent.click(screen.getByRole("button", { name: "Start bootstrap install" }));
    await waitFor(() => {
      expect(runBootstrapInstall).toHaveBeenCalledWith(runId, stageId, expect.objectContaining({
        idempotency_key: `bootstrap-install-${runId}-${stageId}`,
      }));
    });
  });

  it("prevents duplicate click while working", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({ status: "not_started" }));
    vi.mocked(runBootstrapInstall).mockImplementation(() => new Promise(() => {}));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} runStateVersion={5} />);
    await waitFor(() => screen.getByRole("button", { name: "Start bootstrap install" }));
    fireEvent.click(screen.getByRole("button", { name: "Start bootstrap install" }));
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
  });

  it("renders artifact links when artifact_ids present", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "COMPLETED", artifact_ids: ["artifact-log-001", "artifact-summary-001"],
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getAllByText(/Artifact/).length).toBeGreaterThan(0));
  });

  it("shows backend error on status fetch failure", async () => {
    vi.mocked(getBootstrapInstallStatus).mockRejectedValue(new Error("network error"));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => expect(screen.getByText(/could not be loaded/)).toBeInTheDocument());
  });

  it("reconnects from status re-fetch after error", async () => {
    vi.mocked(getBootstrapInstallStatus)
      .mockRejectedValueOnce(new ApiClientError("error", 500, "GET", "/status"))
      .mockResolvedValueOnce(makeStatus({ status: "COMPLETED", exit_code: 0 }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => {
      expect(screen.queryByText(/could not be loaded/)).not.toBeInTheDocument();
    }, { timeout: 8000 });
  });

  it("shows stale state version warning on 409", async () => {
    vi.mocked(getBootstrapInstallStatus).mockReset();
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({ status: "not_started" }));
    vi.mocked(runBootstrapInstall).mockReset();
    vi.mocked(runBootstrapInstall).mockRejectedValue(
      new ApiClientError("STALE_STATE_VERSION", 409, "POST", "/bootstrap",
        JSON.stringify({ detail: { error_code: "STALE_STATE_VERSION", message: "stale" } }))
    );
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} runStateVersion={5} />);
    const btn = await screen.findByRole("button", { name: /start bootstrap/i }, { timeout: 3000 });
    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText(/Refresh the authoritative state/)).toBeInTheDocument(), { timeout: 3000 });
  });

  it("shows error message on install failure", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({ status: "not_started" }));
    vi.mocked(runBootstrapInstall).mockRejectedValue(
      new ApiClientError("server error", 500, "POST", "/bootstrap")
    );
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} runStateVersion={5} />);
    await waitFor(() => screen.getByRole("button", { name: "Start bootstrap install" }));
    fireEvent.click(screen.getByRole("button", { name: "Start bootstrap install" }));
    await waitFor(() => expect(screen.getByText(/could not be started/)).toBeInTheDocument());
  });

  it("uses backend g07_status and lifecycle_script_audit_ref", async () => {
    vi.mocked(getBootstrapInstallStatus).mockResolvedValue(makeStatus({
      status: "COMPLETED", g07_status: "approved", lifecycle_script_audit_ref: "artifact-lifecycle",
    }));
    render(<BootstrapInstallPanel runId={runId} stageId={stageId} />);
    await waitFor(() => {
      expect(screen.getByText("approved")).toBeInTheDocument();
      expect(screen.getByText("artifact-lifecycle")).toBeInTheDocument();
    });
  });
});
