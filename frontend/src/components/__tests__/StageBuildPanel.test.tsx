import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StageBuildPanel } from "@/components/StageBuildPanel";
import { ApiClientError } from "@/api/client";
import { getStageBuildMatrix, startStageBuild } from "@/api/stageBuild";

vi.mock("@/api/stageBuild", () => ({
  cancelStageBuild: vi.fn(),
  getStageBuildMatrix: vi.fn(),
  startStageBuild: vi.fn(),
}));

const response = {
  build_id: "build-1",
  run_id: "run-1",
  stage_id: "stage-1",
  status: "passed",
  targets: [
    { target_id: "build:app", project: "app", configuration: "production", kind: "prod_build", mandatory: true, supported: true, command_id: "build:prod", executable: "ng", arguments: ["build", "--prod"], blocker: null },
    { target_id: "conditional:ssr", project: "app", configuration: null, kind: "conditional", mandatory: false, supported: false, command_id: "", executable: "", arguments: [], blocker: "NOT_CONFIGURED" },
  ],
  results: [
    { target_id: "build:app", status: "passed", exit_code: 0, duration_ms: 120000, warnings: [], errors: [], output_location: "dist/app", artifact_ids: ["artifact-1"], blocker: null },
  ],
  artifact_ids: ["artifact-1"],
  artifact_checksums: { "artifact-1": "sha256:build-out" },
  state_version: 2,
  event_sequence: 3,
  idempotent_replay: false,
};

describe("StageBuildPanel", () => {
  it("shows loading state initially", () => {
    vi.mocked(getStageBuildMatrix).mockReturnValue(new Promise(() => {}));
    render(<StageBuildPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(screen.getByText("Loading build matrix...")).toBeInTheDocument();
  });

  it("renders build targets with mandatory and conditional labels", async () => {
    vi.mocked(getStageBuildMatrix).mockResolvedValue(response);
    render(<StageBuildPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("build:app")).toBeInTheDocument();
    expect(await screen.findByText("Mandatory")).toBeInTheDocument();
    expect(await screen.findByText("conditional:ssr")).toBeInTheDocument();
    expect(await screen.findByText("not configured")).toBeInTheDocument();
    expect(screen.getByText(/120000 ms/)).toBeInTheDocument();
  });

  it("shows empty state when no build exists", async () => {
    vi.mocked(getStageBuildMatrix).mockRejectedValue(new ApiClientError("not found", 404));
    render(<StageBuildPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("No build matrix has been started yet.")).toBeInTheDocument();
  });

  it("shows error state on backend failure", async () => {
    vi.mocked(getStageBuildMatrix).mockRejectedValue(new ApiClientError("server error", 500));
    render(<StageBuildPanel runId="run-1" stageId="stage-1" stateVersion={1} connectionStatus="open" />);
    expect(await screen.findByText("Stage build matrix could not be loaded.")).toBeInTheDocument();
  });

  it("starts build with authoritative state version", async () => {
    vi.mocked(getStageBuildMatrix).mockRejectedValue(new ApiClientError("not found", 404));
    vi.mocked(startStageBuild).mockResolvedValue(response);
    render(<StageBuildPanel runId="run-1" stageId="stage-1" stateVersion={5} connectionStatus="reconnecting" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Run build matrix" })).toBeEnabled());
    screen.getByRole("button", { name: "Run build matrix" }).click();
    await waitFor(() => expect(startStageBuild).toHaveBeenCalledWith("run-1", "stage-1", expect.objectContaining({ expected_state_version: 5 })));
  });
});
