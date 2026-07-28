import { render, screen } from "@testing-library/react";
import { AssistantPanel } from "@/components/AssistantPanel";

vi.mock("@/api/assistant", () => ({
  getAssistantMessages: vi.fn().mockResolvedValue({ run_id: "run-1", conversation_id: "conversation-1", messages: [{
  message_id: "message-1", message_order: 1, conversation_id: "conversation-1", run_id: "run-1", role: "assistant", answer: "The migration is in the Preflight Snapshot phase at G02 Source Integrity Approval.", current_phase: "Preflight Snapshot", current_stage: "G02 Source Integrity Approval", workflow_status: "SOURCE_VALIDATED", current_gate: "G02 pending", current_blocker: "none", next_permitted_action: "Record a G02 reviewer decision through the governed cockpit control.", workflow_state_version: 8, stale: false, evidence_references: [{ artifact_id: "artifact-g02", checksum: "sha256:g02", label: "03_g02/g02_evidence_index.json" }, { artifact_id: "artifact-integrity", checksum: "sha256:integrity", label: "03_g02/source_integrity_verification.json" }], citations: [{ artifact_id: "artifact-g02", checksum: "sha256:g02", label: "03_g02/g02_evidence_index.json", excerpt_id: "excerpt-g02", checksum_sha256: "sha256:g02", stage_key: "G02", locator: { kind: "line_range", value: "1-1" }, proof_label: "approved_evidence_supported" }, { artifact_id: "artifact-integrity", checksum: "sha256:integrity", label: "03_g02/source_integrity_verification.json", excerpt_id: "excerpt-integrity", checksum_sha256: "sha256:integrity", stage_key: "G02", locator: { kind: "line_range", value: "1-1" }, proof_label: "approved_evidence_supported" }], proof_label: "authoritative persisted fact", usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_input_cost: 0, estimated_output_cost: 0, estimated_total_cost: 0 }, response_status: "completed", failure_reason: null,
  }] }), sendAssistantMessage: vi.fn() }));

describe("AssistantPanel authoritative rendering", () => {
  beforeEach(() => {
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
    expect(screen.getByText("Operational statistics unavailable")).toBeInTheDocument();
  });
});
