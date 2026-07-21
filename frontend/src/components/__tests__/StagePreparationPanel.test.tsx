import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import { StagePreparationPanel } from "../StagePreparationPanel";
import { prepareStage, decideG07, createSandbox, getG07Status } from "@/api/stages";
import { ApiClientError } from "@/api/client";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

vi.mock("@/api/stages", () => ({
  prepareStage: vi.fn(), decideG07: vi.fn(), createSandbox: vi.fn(),
  getG07Status: vi.fn().mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", gate_id: "G07", gate_version: "g07-v1", status: "pending", decision: null, package: { stage_id: "persisted-stage-7", plan_version: "7", source_fingerprint: "sha256:input" }, state_version: 7, event_sequence: 12, idempotent_replay: false, stale_reason: null, comment: null }),
}));

const state = { run_id: "run-1", state_version: 7, workflow_events: [], artifacts: [], status: "WAITING", run_phase: "STAGED_MIGRATION", phase_status: "running", approval_status: "not_required", repair_status: "not_required", preflight_id: "p", source_path: "", target_output_path: "", graph_thread_id: "g", created_at: "now", updated_at: "now" } as unknown as AuthoritativeRunStateDto;

describe("StagePreparationPanel F1", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getG07Status).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", gate_id: "G07", gate_version: "g07-v1", status: "pending", decision: null, package: { stage_id: "persisted-stage-7", stage_key: "angular-18-to-19", source_version_family: "18.x", target_version_family: "19.x", plan_version: "plan-7", source_fingerprint: "sha256:input" }, state_version: 7, event_sequence: 12, idempotent_replay: false, stale_reason: null, comment: null });
    vi.mocked(prepareStage).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", stage_key: "angular-18-to-19", status: "waiting_approval", state_version: 8, event_sequence: 13, plan: { migration_plan_id: "plan-7" }, idempotent_replay: false });
    vi.mocked(decideG07).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", gate_id: "G07", gate_version: "g07-v1", status: "approved", decision: "approved", package: { stage_id: "persisted-stage-7" }, state_version: 8, event_sequence: 13, idempotent_replay: false, stale_reason: null, comment: null, decision_id: "decision-1" });
    vi.mocked(createSandbox).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", sandbox_path: "C:\\private", status: "creating_sandbox", state_version: 9, event_sequence: 14, verification: null, idempotent_replay: false });
  });

  it("mount is read-only and uses persisted stage identity", async () => {
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(getG07Status).toHaveBeenCalledWith("run-1", "persisted-stage-7"));
    expect(prepareStage).not.toHaveBeenCalled();
    expect(decideG07).not.toHaveBeenCalled();
    expect(createSandbox).not.toHaveBeenCalled();
    expect(screen.getByText("G07 boundary review")).toBeInTheDocument();
  });

  it("does not render a raw filesystem path", async () => {
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(getG07Status).toHaveBeenCalled());
    expect(screen.queryByText(/C:\\\\|\/home\/|sandbox_path/i)).not.toBeInTheDocument();
  });

  it("prepare uses current bindings and reuses its key on retry", async () => {
    vi.mocked(prepareStage).mockRejectedValueOnce(new Error("timeout"));
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(screen.getByText("Prepare stage")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Prepare stage"));
    await waitFor(() => expect(prepareStage).toHaveBeenCalledTimes(1));
    const first = vi.mocked(prepareStage).mock.calls[0][2];
    expect(first).toMatchObject({ expected_state_version: 7, stage_key: "angular-18-to-19", source_version_family: "18.x", target_version_family: "19.x", plan_version: "plan-7" });
    fireEvent.click(screen.getByText("Prepare stage"));
    await waitFor(() => expect(prepareStage).toHaveBeenCalledTimes(2));
    expect(vi.mocked(prepareStage).mock.calls[1][2].idempotency_key).toBe(first.idempotency_key);
  });

  it("supports all decisions and enforces normalized comments", async () => {
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(screen.getByText("Record G07 decision")).toBeInTheDocument());
    const select = screen.getByLabelText("Decision");
    const comment = screen.getByLabelText("Comment");
    fireEvent.change(select, { target: { value: "approved_with_comment" } });
    fireEvent.change(comment, { target: { value: "   " } });
    fireEvent.click(screen.getByText("Record G07 decision"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/non-empty comment/i));
    fireEvent.change(comment, { target: { value: "  reviewed  " } });
    fireEvent.click(screen.getByText("Record G07 decision"));
    await waitFor(() => expect(decideG07).toHaveBeenCalledTimes(1));
    expect(vi.mocked(decideG07).mock.calls[0][1]).toMatchObject({ decision: "approved_with_comment", comment: "reviewed", stage_id: "persisted-stage-7", expected_state_version: 7 });
  });

  it("gates sandbox on current approved G07 and uses its binding", async () => {
    vi.mocked(getG07Status).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", gate_id: "G07", gate_version: "g07-v2", status: "approved", decision: "approved", package: { stage_id: "persisted-stage-7", stage_key: "angular-18-to-19", source_version_family: "18.x", target_version_family: "19.x", plan_version: "plan-7" }, state_version: 11, event_sequence: 20, idempotent_replay: false, stale_reason: null, comment: null });
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(screen.getByText("Prepare stage")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Prepare stage"));
    await waitFor(() => expect(screen.getByText("Create sandbox")).toBeInTheDocument());
    expect(screen.getByText("Create sandbox")).not.toBeDisabled();
    fireEvent.click(screen.getByText("Create sandbox"));
    await waitFor(() => expect(createSandbox).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createSandbox).mock.calls[0][2]).toMatchObject({ expected_state_version: 11 });
  });

  it("reloads authority after a stale conflict without resubmitting", async () => {
    const refreshAuthority = vi.fn().mockResolvedValue(undefined);
    vi.mocked(decideG07).mockRejectedValueOnce(new ApiClientError("stale", 409));
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} refreshAuthoritativeState={refreshAuthority} />);
    await waitFor(() => expect(screen.getByText("Record G07 decision")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Record G07 decision"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/state changed/i));
    expect(decideG07).toHaveBeenCalledTimes(1);
    expect(refreshAuthority).toHaveBeenCalledTimes(1);
    expect(getG07Status).toHaveBeenCalledTimes(2);
  });

  it("does not treat a sandbox POST response as authoritative ready", async () => {
    vi.mocked(getG07Status).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", gate_id: "G07", gate_version: "g07-v2", status: "approved", decision: "approved", package: { stage_id: "persisted-stage-7", stage_key: "angular-18-to-19", source_version_family: "18.x", target_version_family: "19.x", plan_version: "plan-7" }, state_version: 11, event_sequence: 20, idempotent_replay: false, stale_reason: null, comment: null });
    vi.mocked(createSandbox).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", sandbox_path: "C:\\private", status: "sandbox_ready", state_version: 12, event_sequence: 21, verification: null, idempotent_replay: false });
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(screen.getByText("Prepare stage")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Prepare stage"));
    await waitFor(() => expect(screen.getByText("Create sandbox")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Create sandbox"));
    await waitFor(() => expect(createSandbox).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Sandbox is ready. Proceed to bootstrap installation.")).not.toBeInTheDocument();
  });

  it("uses the current durable ready event and ignores another stage", async () => {
    const readyState = { ...state, workflow_events: [{ event_id: "ready-1", run_id: "run-1", stage_id: "other-stage", event_type: "STAGE_SANDBOX_READY", occurred_at: "now", sequence: 20, payload: {} }] } as unknown as AuthoritativeRunStateDto;
    const { rerender } = render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={readyState} />);
    await waitFor(() => expect(screen.getByText("Prepare stage")).toBeInTheDocument());
    expect(screen.queryByText("Sandbox is ready. Proceed to bootstrap installation.")).not.toBeInTheDocument();
    rerender(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={{ ...readyState, workflow_events: [{ ...readyState.workflow_events[0], stage_id: "persisted-stage-7" }] } as AuthoritativeRunStateDto} />);
    expect(await screen.findByText("Sandbox is ready. Proceed to bootstrap installation.")).toBeInTheDocument();
  });

  it("stale durable events block sandbox authority", async () => {
    const staleState = { ...state, workflow_events: [{ event_id: "stale-1", run_id: "run-1", stage_id: "persisted-stage-7", event_type: "G07_STALE", occurred_at: "now", sequence: 20, payload: {} }] } as unknown as AuthoritativeRunStateDto;
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={staleState} />);
    await waitFor(() => expect(screen.getAllByText(/stale/i).length).toBeGreaterThan(0));
    expect(screen.queryByText("Create sandbox")).not.toBeInTheDocument();
  });

  it("displays copy and verification evidence without exposing paths", async () => {
    vi.mocked(getG07Status).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", gate_id: "G07", gate_version: "g07-v2", status: "approved", decision: "approved", package: { stage_id: "persisted-stage-7", stage_key: "angular-18-to-19", source_version_family: "18.x", target_version_family: "19.x", plan_version: "plan-7", artifact_ids: ["stage-start-1"], artifact_links: { "stage-start-1": "/api/v1/artifacts/stage-start-1" } }, state_version: 11, event_sequence: 20, idempotent_replay: false, stale_reason: null, comment: null });
    vi.mocked(createSandbox).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", sandbox_path: "C:\\secret\\sandbox", status: "creating_sandbox", state_version: 12, event_sequence: 21, verification: { workspace_alias: "stage_workspace", copy_status: "completed", file_count: 42, total_size_bytes: 4096, source_fingerprint: "sha256:source", sandbox_fingerprint: "sha256:sandbox", verified: true, reconstruction: false, copy_report_artifact_id: "copy-1", copy_report_checksum: "sha256:copy", verification_artifact_id: "verify-1", verification_checksum: "sha256:verify", workspace_path: "C:\\secret\\sandbox" }, idempotent_replay: false });
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(screen.getByText("Prepare stage")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Prepare stage"));
    await waitFor(() => expect(screen.getByText("Create sandbox")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Create sandbox"));
    await waitFor(() => expect(screen.getByText("stage_workspace")).toBeInTheDocument());
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("sha256:source")).toBeInTheDocument();
    expect(screen.getByText("copy-1 sha256:copy")).toBeInTheDocument();
    expect(screen.queryByText(/C:\\secret/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "stage-start-1" })).toHaveAttribute("rel", "noreferrer");
  });

  it("provides accessible keyboard tabs", async () => {
    vi.mocked(prepareStage).mockResolvedValue({ run_id: "run-1", stage_id: "persisted-stage-7", stage_key: "angular-18-to-19", status: "waiting_approval", state_version: 8, event_sequence: 13, plan: { id: "p" }, idempotent_replay: false });
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(screen.getByText("Prepare stage")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Prepare stage"));
    await waitFor(() => expect(screen.getByRole("tablist")).toBeInTheDocument());
    const tabs = screen.getAllByRole("tab");
    tabs[0].focus();
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" });
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs[1], { key: "End" });
    expect(tabs[2]).toHaveAttribute("aria-selected", "true");
    expect(tabs[2]).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "stage-tab-input");
  });

  it("shows an explicit unavailable state when sandbox evidence is missing", async () => {
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(screen.getByText("Prepare stage")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Prepare stage"));
    await waitFor(() => expect(screen.getByText("Sandbox evidence")).toBeInTheDocument());
    expect(screen.getByText("Copy and verification evidence not yet available.")).toBeInTheDocument();
  });

  it("renders exact current profile bindings instead of placeholders", async () => {
    render(<StagePreparationPanel runId="run-1" stageId="persisted-stage-7" initialState={state} />);
    await waitFor(() => expect(screen.getByText("Prepare stage")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Prepare stage"));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Profile" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Profile" }));
    expect(screen.getByText("18.x")).toBeInTheDocument();
    expect(screen.getByText("19.x")).toBeInTheDocument();
    expect(screen.getByText("plan-7")).toBeInTheDocument();
    expect(screen.queryByText("detected")).not.toBeInTheDocument();
    expect(screen.queryByText("resolved")).not.toBeInTheDocument();
    expect(screen.queryByText("latest")).not.toBeInTheDocument();
  });
});
