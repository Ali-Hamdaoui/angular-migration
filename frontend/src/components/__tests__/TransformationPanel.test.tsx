import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TransformationPanel } from "@/components/TransformationPanel";
import {
  decideTransformationGate,
  decideTransformationPrompt,
  getTransformation,
} from "@/api/transformation";

vi.mock("@/api/transformation", () => ({
  getTransformation: vi.fn(),
  decideTransformationGate: vi.fn(),
  decideTransformationPrompt: vi.fn(),
  cancelTransformation: vi.fn(),
  restartTransformation: vi.fn(),
}));

const projection = {
  run_id: "run-1",
  continuation_id: "transform-1",
  stage_id: "stage-1",
  status: "waiting_gate" as const,
  current_node: "wait_g07",
  state_version: 3,
  stage_status: "preparing",
  source_version: "18.x",
  target_version: "19.x",
  checkpoint_kind: "pre_bootstrap",
  workspace_fingerprint: "sha256:workspace",
  active_gate: "G07",
  active_gate_package_checksum: "sha256:g07",
  active_command_id: null,
  active_command_status: null,
  active_prompt_id: null,
  active_prompt_checksum: null,
  active_prompt_text: null,
  active_prompt_options: [],
  active_prompt_explanation: null,
  repair_attempt_id: null,
  repair_status: null,
  repair_risk_level: null,
  repair_proposal_checksum: null,
  repair_review_checksum: null,
  repair_apply_checksum: null,
  repair_validation_checksum: null,
  route_stages: [
    {
      stage_id: "stage-1",
      source_version: "18.x",
      target_version: "19.x",
      status: "preparing",
    },
  ],
  sealed_chain_hash: null,
  last_error_code: null,
  cancel_requested_at: null,
};

describe("TransformationPanel", () => {
  afterEach(() => vi.resetAllMocks());

  it("projects durable node, command, gate, and checkpoint status", async () => {
    vi.mocked(getTransformation).mockResolvedValue(projection);
    render(<TransformationPanel runId="run-1" workflowEvents={[]} />);

    expect(await screen.findByRole("heading", { name: "18.x to 19.x" })).toBeInTheDocument();
    expect(screen.getByText("waiting_gate / wait_g07")).toBeInTheDocument();
    expect(screen.getByText("G07")).toBeInTheDocument();
    expect(screen.getByText("pre_bootstrap")).toBeInTheDocument();
    expect(screen.getByText("sha256:workspace")).toBeInTheDocument();
    expect(screen.getByText("18.x to 19.x: preparing")).toBeInTheDocument();
  });

  it("directs operators when no continuation exists", async () => {
    vi.mocked(getTransformation).mockRejectedValue(new Error("Backend request failed (404)"));
    render(<TransformationPanel runId="run-1" workflowEvents={[]} />);

    expect(await screen.findByText("Transformer starts after accepted G06.")).toBeInTheDocument();
  });

  it("submits the current G07 package and fingerprint", async () => {
    vi.mocked(getTransformation).mockResolvedValue(projection);
    vi.mocked(decideTransformationGate).mockResolvedValue({});
    render(<TransformationPanel runId="run-1" workflowEvents={[]} />);

    fireEvent.click(await screen.findByRole("button", { name: "Approve G07" }));

    await waitFor(() => expect(decideTransformationGate).toHaveBeenCalledWith(
      "run-1",
      "G07",
      expect.objectContaining({
        expected_state_version: 3,
        package_checksum: "sha256:g07",
        workspace_fingerprint: "sha256:workspace",
        decision: "approve",
      }),
    ));
  });

  it("submits only a bounded Angular prompt option", async () => {
    vi.mocked(getTransformation).mockResolvedValue({
      ...projection,
      status: "waiting_prompt",
      active_gate: null,
      active_gate_package_checksum: null,
      active_prompt_id: "prompt-1",
      active_prompt_checksum: "sha256:prompt",
      active_prompt_text: "Would you like to migrate?",
      active_prompt_options: [{ option_id: "yes", label: "Yes" }],
      active_prompt_explanation: {
        summary: "Angular needs a decision.",
        option_effects: ["Yes reruns the command."],
        risk_note: "Review the migration.",
        source: "azure_openai",
      },
    });
    vi.mocked(decideTransformationPrompt).mockResolvedValue({});
    render(<TransformationPanel runId="run-1" workflowEvents={[]} />);

    fireEvent.click(await screen.findByRole("button", { name: "Yes" }));

    await waitFor(() => expect(decideTransformationPrompt).toHaveBeenCalledWith(
      "run-1",
      "prompt-1",
      expect.objectContaining({
        expected_state_version: 3,
        prompt_checksum: "sha256:prompt",
        selected_option_id: "yes",
      }),
    ));
  });
});
