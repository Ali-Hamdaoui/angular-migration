import { readFileSync } from "node:fs";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AssistantDock, AssistantPanel } from "@/components/AssistantPanel";
import { getAssistantMessages, sendAssistantMessage, streamAssistantEvents } from "@/api/assistant";
import { ApiClientError } from "@/api/client";

const shellCss = readFileSync("src/components/ControlTowerShell.module.css", "utf8");
const layoutCss = readFileSync("src/components/control-tower/ControlTowerLayout.module.css", "utf8");

vi.mock("@/api/assistant", () => ({
  getAssistantMessages: vi.fn().mockResolvedValue({ run_id: "run-1", conversation_id: "conversation-1", messages: [{
    message_id: "message-1", model: "gpt-5-mini", message_order: 1, conversation_id: "conversation-1", run_id: "run-1", role: "assistant", answer: "The migration is in the Preflight Snapshot phase at G02 Source Integrity Approval.", current_phase: "Preflight Snapshot", current_stage: "G02 Source Integrity Approval", workflow_status: "SOURCE_VALIDATED", current_gate: "G02 pending", current_blocker: "none", next_permitted_action: "Record a G02 reviewer decision through the governed cockpit control.", workflow_state_version: 8, stale: false, evidence_references: [{ artifact_id: "artifact-g02", checksum: "sha256:g02", label: "03_g02/g02_evidence_index.json" }, { artifact_id: "artifact-integrity", checksum: "sha256:integrity", label: "03_g02/source_integrity_verification.json" }], proof_label: "authoritative persisted fact", usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 }, response_status: "completed", failure_reason: null,
    next_step_proposals: [],
  }] }),
  sendAssistantMessage: vi.fn(),
  streamAssistantEvents: vi.fn(() => new Promise<never>(() => undefined)),
}));

describe("AssistantPanel authoritative rendering", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(sendAssistantMessage).mockReset();
    vi.mocked(streamAssistantEvents).mockReset();
    vi.mocked(streamAssistantEvents).mockImplementation(() => new Promise<never>(() => undefined));
  });

  it("renders current progress, separated evidence, and authoritative zero usage", async () => {
    render(<AssistantPanel runId="run-1" phase="PREFLIGHT_SNAPSHOT" stateVersion={8} workflowStatus="SOURCE_VALIDATED" />);

    expect(await screen.findByText(/Preflight Snapshot · G02 Source Integrity Approval · G02 pending/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "03_g02/g02_evidence_index.json" })).toHaveAttribute("href", expect.stringContaining("artifact-g02"));
    expect(screen.getByRole("link", { name: "03_g02/source_integrity_verification.json" })).toHaveAttribute("href", expect.stringContaining("artifact-integrity"));
    expect(screen.getAllByText(/gpt-5-mini/).length).toBeGreaterThan(0);
    expect(screen.getByText("Operational statistics unavailable")).toBeInTheDocument();
  });

  it("renders an assistant response without next-step proposals outside the app router", async () => {
    render(<AssistantPanel runId="run-1" phase="PREFLIGHT_SNAPSHOT" stateVersion={8} workflowStatus="SOURCE_VALIDATED" />);

    expect(await screen.findByText(/The migration is in the Preflight Snapshot phase/)).toBeInTheDocument();
  });

  it("restores the floating dock state without putting the Assistant in navigation", async () => {
    localStorage.setItem("amfa:assistant:run-1:open", "true");
    render(<AssistantDock runId="run-1" phase="PREFLIGHT_SNAPSHOT" stateVersion={8} workflowStatus="SOURCE_VALIDATED" />);
    expect(await screen.findByRole("dialog", { name: "Migration Follow-up Assistant" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Migration Follow-up Assistant" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Open Assistant" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close Assistant" }));
    expect(screen.getByRole("button", { name: "Open Assistant" })).toBeInTheDocument();
  });

  it("minimizes and restores the single mounted panel without another history load", async () => {
    localStorage.setItem("amfa:assistant:run-1:presentation", "expanded");
    render(<AssistantDock runId="run-1" />);
    expect(await screen.findByRole("button", { name: "Minimize Assistant" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Migration Follow-up Assistant", hidden: true })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Minimize Assistant" }));
    expect(screen.getByText("Migration Assistant")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open Assistant" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand Assistant" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Expand Assistant" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Migration Follow-up Assistant", hidden: true })).toHaveLength(1);
    expect(getAssistantMessages).toHaveBeenCalledTimes(1);
  });

  it("keeps closed and minimized launchers in the sidebar flow while the expanded dialog stays fixed", async () => {
    const { container } = render(
      <aside className="controlTowerSidebar">
        <nav aria-label="Run sections" />
        <div className="controlTowerAssistantSlot"><AssistantDock runId="run-1" /></div>
      </aside>,
    );

    const slot = container.querySelector(".controlTowerAssistantSlot") as HTMLElement;
    expect(slot).toContainElement(screen.getByRole("button", { name: "Open Assistant" }));
    expect(layoutCss).toMatch(/:global\(\.controlTowerAssistantSlot\) \[data-assistant-presentation\][^{]*\{[^}]*position:\s*static/);
    expect(layoutCss).toMatch(/@media \(max-width: 767px\)[^{]*\{[\s\S]*:global\(\.controlTowerAssistantSlot\) \[data-assistant-presentation\][^{]*\{[^}]*width:\s*100%/);
    expect(shellCss).toMatch(/\.assistantPopup\s*\{[^}]*position:\s*fixed/);

    fireEvent.click(screen.getByRole("button", { name: "Open Assistant" }));
    expect(await screen.findByRole("dialog", { name: "Migration Follow-up Assistant" })).toBeInTheDocument();
  });

  it("keeps the composer outside one scrollable conversation region", async () => {
    render(<AssistantPanel runId="run-1" />);
    const conversation = await screen.findByRole("region", { name: "Assistant conversation" });
    expect(conversation).toContainElement(screen.getByLabelText("Suggested assistant questions"));
    expect(conversation).not.toContainElement(screen.getByRole("textbox", { name: "Ask about this migration" }));
    expect(screen.getAllByRole("region")).toHaveLength(3);
  });

  it("keeps a 503 visible and exposes the existing retry action", async () => {
    vi.mocked(sendAssistantMessage).mockRejectedValueOnce(new ApiClientError("failed", 503, "POST", "/api/v1/runs/run-1/assistant/messages"));
    render(<AssistantPanel runId="run-1" />);
    fireEvent.change(await screen.findByRole("textbox", { name: "Ask about this migration" }), { target: { value: "Why?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Assistant request failed POST /api/v1/runs/run-1/assistant/messages returned 503");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("keeps retry available when the stream disconnects after a 503 request failure", async () => {
    let rejectStream!: (reason?: unknown) => void;
    vi.mocked(streamAssistantEvents).mockReturnValueOnce(new Promise<never>((_, reject) => { rejectStream = reject; }));
    vi.mocked(sendAssistantMessage).mockRejectedValueOnce(new ApiClientError("failed", 503, "POST", "/api/v1/runs/run-1/assistant/messages"));
    render(<AssistantPanel runId="run-1" />);

    fireEvent.change(await screen.findByRole("textbox", { name: "Ask about this migration" }), { target: { value: "Why?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/POST \/api\/v1\/runs\/run-1\/assistant\/messages returned 503/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();

    rejectStream(new Error("stream disconnected"));

    expect(await screen.findByText("Reconnecting to persisted conversation…")).toBeInTheDocument();
    expect(screen.getByText(/POST \/api\/v1\/runs\/run-1\/assistant\/messages returned 503/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("clears a visible request failure when a different run loads", async () => {
    vi.mocked(sendAssistantMessage).mockRejectedValueOnce(new ApiClientError("failed", 503, "POST", "/api/v1/runs/run-1/assistant/messages"));
    const { rerender } = render(<AssistantPanel runId="run-1" />);
    fireEvent.change(await screen.findByRole("textbox", { name: "Ask about this migration" }), { target: { value: "Why did run 1 fail?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/POST \/api\/v1\/runs\/run-1\/assistant\/messages returned 503/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();

    vi.mocked(getAssistantMessages).mockResolvedValueOnce({ run_id: "run-2", conversation_id: "conversation-2", messages: [] });
    rerender(<AssistantPanel runId="run-2" />);

    expect(await screen.findByText("Ask any read-only question about this migration.")).toBeInTheDocument();
    expect(screen.queryByText(/POST \/api\/v1\/runs\/run-1\/assistant\/messages returned 503/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("ignores a late run-1 rejection while a run-2 request is pending", async () => {
    let rejectRun1!: (reason?: unknown) => void;
    const run1Request = new Promise<Awaited<ReturnType<typeof sendAssistantMessage>>>((_, reject) => { rejectRun1 = reject; });
    vi.mocked(sendAssistantMessage)
      .mockReturnValueOnce(run1Request)
      .mockReturnValueOnce(new Promise<Awaited<ReturnType<typeof sendAssistantMessage>>>(() => undefined));
    const { rerender } = render(<AssistantPanel runId="run-1" />);
    fireEvent.change(await screen.findByRole("textbox", { name: "Ask about this migration" }), { target: { value: "Run 1 question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByRole("status")).toHaveTextContent("Assistant is thinking");

    vi.mocked(getAssistantMessages).mockResolvedValueOnce({ run_id: "run-2", conversation_id: "conversation-2", messages: [] });
    rerender(<AssistantPanel runId="run-2" />);
    expect(await screen.findByText("Ask any read-only question about this migration.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Ask about this migration" }), { target: { value: "Run 2 question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await act(async () => {
      rejectRun1(new ApiClientError("failed", 503, "POST", "/api/v1/runs/run-1/assistant/messages"));
      await run1Request.catch(() => undefined);
    });

    expect(screen.getByRole("article", { name: "user message" })).toHaveTextContent("Run 2 question");
    expect(screen.getByRole("status")).toHaveTextContent("Assistant is thinking");
    expect(screen.queryByText(/POST \/api\/v1\/runs\/run-1\/assistant\/messages returned 503/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("shows transient thinking, keeps the optimistic question, and sends Enter once", async () => {
    let resolve!: () => void;
    vi.mocked(sendAssistantMessage).mockReturnValueOnce(new Promise<Awaited<ReturnType<typeof sendAssistantMessage>>>((done) => { resolve = () => done({} as Awaited<ReturnType<typeof sendAssistantMessage>>); }));
    render(<AssistantPanel runId="run-1" />);
    const textbox = await screen.findByRole("textbox", { name: "Ask about this migration" });
    fireEvent.change(textbox, { target: { value: "What is next?" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(screen.getByRole("article", { name: "user message" })).toHaveTextContent("What is next?");
    expect(textbox).toHaveValue("");
    expect(screen.getByRole("status")).toHaveTextContent("Assistant is thinking");
    expect(sendAssistantMessage).toHaveBeenCalledTimes(1);
    resolve();
    await waitFor(() => expect(screen.queryByText(/Assistant is thinking/)).not.toBeInTheDocument());
  });

  it("keeps suggestions compact and avoids repeated user metadata", async () => {
    render(<AssistantPanel runId="run-1" />);
    expect((await screen.findByLabelText("Suggested assistant questions")).querySelectorAll("button")).toHaveLength(3);
    fireEvent.change(screen.getByRole("textbox", { name: "Ask about this migration" }), { target: { value: "Why?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("article", { name: "user message" })).not.toHaveTextContent("Blocker:");
  });

  it("opens an expanded modal with initial focus, closes on Escape, and returns focus to launcher", async () => {
    render(<AssistantDock runId="run-1" />);
    const launcher = screen.getByRole("button", { name: "Open Assistant" });
    fireEvent.click(launcher);
    const dialog = await screen.findByRole("dialog", { name: "Migration Follow-up Assistant" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Close Assistant" })).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Open Assistant" })).toHaveFocus();
  });

  it("keeps focus inside the expanded drawer when tabbing from the last control", async () => {
    render(<AssistantDock runId="run-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Open Assistant" }));
    const dialog = await screen.findByRole("dialog", { name: "Migration Follow-up Assistant" });
    const controls = Array.from(dialog.querySelectorAll<HTMLElement>('button, textarea, select, input, [tabindex]:not([tabindex="-1"])')).filter((item) => !item.hasAttribute("disabled"));
    const last = controls.at(-1)!;
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(screen.getByRole("button", { name: "Minimize Assistant" })).toHaveFocus();
  });

  it("shows response hierarchy before technical response details", async () => {
    render(<AssistantPanel runId="run-1" />);
    expect(await screen.findByText("Current state")).toBeInTheDocument();
    expect(screen.getByText("What is waiting")).toBeInTheDocument();
    expect(screen.getByText("Why it is blocked")).toBeInTheDocument();
    expect(screen.getByText("Next permitted action")).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.queryByText(/Capability:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Response details"));
    expect(screen.getByText("Operational statistics unavailable")).toBeInTheDocument();
  });
});
