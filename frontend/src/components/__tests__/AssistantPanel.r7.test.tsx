import { render, screen } from "@testing-library/react";
import { AssistantPanel } from "@/components/AssistantPanel";
import { getAssistantMessages } from "@/api/assistant";

vi.mock("@/api/assistant", () => ({ getAssistantMessages: vi.fn(), sendAssistantMessage: vi.fn() }));

const user = { message_id: "user-1", message_order: 1, conversation_id: "conversation-1", run_id: "run-1", role: "user", answer: "Where is the migration now?", current_phase: "Baseline", current_stage: "unknown", workflow_status: "RUNNING", current_gate: "unknown", current_blocker: "unknown", next_permitted_action: "unknown", workflow_state_version: 1, stale: false, evidence_references: [], proof_label: "user request", usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 }, response_status: "completed", failure_reason: null, request_id: "original-request", answer_mode: "concise" } as const;
const failed = { ...user, message_id: "failed-1", message_order: 2, role: "assistant", answer: "The Assistant request failed before producing a completed answer.", response_status: "failed", failure_reason: "The governed Assistant provider failed; retry is safe.", error_code: "assistant_provider_failed", correlation_id: "corr-1", request_id: "original-request" } as const;

describe("mounted R7 retry", () => {
  beforeEach(() => {
    vi.mocked(getAssistantMessages).mockResolvedValue({ run_id: "run-1", conversation_id: "conversation-1", messages: [user, failed] } as never);
    class ReplayEventSource { addEventListener() {} removeEventListener() {} close() {} }
    Object.defineProperty(window, "EventSource", { configurable: true, value: ReplayEventSource });
  });

  it("renders a persisted failed response without mounting the app router", async () => {
    render(<AssistantPanel runId="run-1" stateVersion={1} workflowStatus="RUNNING" />);
    expect(await screen.findByText(/assistant_provider_failed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
