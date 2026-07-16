import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BaselineValidationPanel } from "@/components/BaselineValidationPanel";
import { ApiClientError } from "@/api/client";
import { getBaselineTargets, getBaselineValidation, startBaselineValidation } from "@/api/baselineMatrix";
import type { BaselineTargetInventoryResponse } from "@/types/baselineMatrix";
vi.mock("@/api/baselineMatrix", () => ({ cancelBaselineValidation: vi.fn(), getBaselineTargets: vi.fn(), getBaselineValidation: vi.fn(), startBaselineValidation: vi.fn() }));
const targets = { run_id: "run-1", package_json_checksum: "sha256:package", angular_json_present: true, state_version: 1, event_sequence: 1, targets: [{ target_id: "script:test", kind: "test", project: null, configuration: null, command_id: "script__test", executable: "npm", arguments: ["run", "test"], supported: true, blocker: null }, { target_id: "not-configured:lint", kind: "lint", project: null, configuration: null, command_id: "", executable: "", arguments: [], supported: false, blocker: "NOT_CONFIGURED" }] } as unknown as BaselineTargetInventoryResponse;
const response = { validation_id: "validation-1", run_id: "run-1", kind: "test", status: "failed", targets: [targets.targets[0]], results: [{ target_id: "script:test", kind: "test", status: "failed", exit_code: 1, duration_ms: 42, warnings: ["warning"], test_count: 2, failed_tests: ["Header renders"], output_location: "04_workflow_state/log.json", artifact_ids: ["artifact-1"], blocker: null }], parser_summary: { failed: 1 }, artifact_ids: ["artifact-1"], baseline_checksum: "sha256:baseline", state_version: 3, event_sequence: 4, idempotent_replay: false } as never;

describe("BaselineValidationPanel", () => {
  it("shows honest missing lint and failed-test evidence", async () => {
    vi.mocked(getBaselineTargets).mockResolvedValue(targets);
    vi.mocked(getBaselineValidation).mockImplementation(async (runId, kind) => kind === "test" ? response : Promise.reject(new ApiClientError("missing", 404)));
    render(<BaselineValidationPanel runId="run-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("skipped not configured")).toBeInTheDocument();
    expect(await screen.findByText("Failed: Header renders")).toBeInTheDocument();
    expect(screen.getByText(/42 ms/)).toBeInTheDocument();
  });

  it("starts a validation with the authoritative state version", async () => {
    vi.mocked(getBaselineTargets).mockResolvedValue(targets);
    vi.mocked(getBaselineValidation).mockRejectedValue(new ApiClientError("missing", 404));
    vi.mocked(startBaselineValidation).mockResolvedValue(response);
    render(<BaselineValidationPanel runId="run-1" stateVersion={7} connectionStatus="reconnecting" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Run test" })).toBeEnabled());
    screen.getByRole("button", { name: "Run test" }).click();
    await waitFor(() => expect(startBaselineValidation).toHaveBeenCalledWith("run-1", "test", expect.objectContaining({ expected_state_version: 7 })));
    expect(screen.getByText("Connection lost. Reconnecting...")).toBeInTheDocument();
  });
});
