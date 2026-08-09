import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AssistantDock, AssistantPanel } from "@/components/AssistantPanel";
import { getAssistantMessages, sendAssistantMessage } from "@/api/assistant";
import { ApiClientError } from "@/api/client";

vi.mock("@/api/assistant", () => ({
  getAssistantMessages: vi.fn().mockResolvedValue({ run_id: "run-1", conversation_id: "conversation-1", messages: [{
    message_id: "message-1", model: "gpt-5-mini", message_order: 1, conversation_id: "conversation-1", run_id: "run-1", role: "assistant", answer: "The migration is in the Preflight Snapshot phase at G02 Source Integrity Approval.", current_phase: "Preflight Snapshot", current_stage: "G02 Source Integrity Approval", workflow_status: "SOURCE_VALIDATED", current_gate: "G02 pending", current_blocker: "none", next_permitted_action: "Record a G02 reviewer decision through the governed cockpit control.", workflow_state_version: 8, stale: false, evidence_references: [{ artifact_id: "artifact-g02", checksum: "sha256:g02", label: "03_g02/g02_evidence_index.json" }, { artifact_id: "artifact-integrity", checksum: "sha256:integrity", label: "03_g02/source_integrity_verification.json" }], proof_label: "authoritative persisted fact", usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 }, response_status: "completed", failure_reason: null,
    next_step_proposals: [],
  }] }), sendAssistantMessage: vi.fn() }));

describe("AssistantPanel authoritative rendering", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    class ReplayEventSource {
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: (() => void) | null = null;
      addEventListener() {}
      removeEventListener() {}
      close() {}
    }
    Object.defineProperty(window, "EventSource", { configurable: true, value: ReplayEventSource });
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

  it("keeps the composer outside one scrollable conversation region", async () => {
    render(<AssistantPanel runId="run-1" />);
    const conversation = await screen.findByRole("region", { name: "Assistant conversation" });
    expect(conversation).toContainElement(screen.getByLabelText("Suggested assistant questions"));
    expect(conversation).not.toContainElement(screen.getByRole("textbox", { name: "Ask about this migration" }));
    expect(screen.getAllByRole("region")).toHaveLength(2);
  });

  it("keeps a 503 visible and exposes the existing retry action", async () => {
    vi.mocked(sendAssistantMessage).mockRejectedValueOnce(new ApiClientError("failed", 503, "POST", "/api/v1/runs/run-1/assistant/messages"));
    render(<AssistantPanel runId="run-1" />);
    fireEvent.change(await screen.findByRole("textbox", { name: "Ask about this migration" }), { target: { value: "Why?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Assistant request failed POST /api/v1/runs/run-1/assistant/messages returned 503");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
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
});
