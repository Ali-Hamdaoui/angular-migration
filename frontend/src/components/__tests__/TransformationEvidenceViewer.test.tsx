import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TransformationEvidenceViewer } from "../TransformationEvidenceViewer";
import { ApiClientError } from "@/api/client";

vi.mock("@/api/transformations", () => ({ getTransformationEvidence: vi.fn(), generateTransformationEvidence: vi.fn() }));

import { getTransformationEvidence, generateTransformationEvidence } from "@/api/transformations";
import type { TransformationEvidenceResponse } from "@/types/transformation";

const mockEvidence: TransformationEvidenceResponse = {
  run_id: "run-1",
  stage_id: "stage-1",
  status: "completed",
  overall_risk_level: "low",
  total_files_changed: 5,
  diff_checksum: "sha256:abc123def456",
  diff_summary: {
    changed_files: [
      { file_path: "src/main.ts", change_type: "modified", classification: "safe", lines_added: 10, lines_removed: 5 },
      { file_path: "src/app.component.ts", change_type: "modified", classification: "high_risk", lines_added: 20, lines_removed: 15 },
      { file_path: "src/unknown.ts", change_type: "added", classification: "unknown", lines_added: 5, lines_removed: 0 },
      { file_path: "package.json", change_type: "modified", classification: "generated", lines_added: 3, lines_removed: 2 },
      { file_path: "src/sensitive.ts", change_type: "modified", classification: "sensitive", lines_added: 1, lines_removed: 1 },
    ],
    files_by_classification: { safe: 1, high_risk: 1, unknown: 1, generated: 1, sensitive: 1 },
  },
  package_change: {
    dependencies_added: ["@angular/core@18.0.0"],
    dependencies_removed: ["@angular/core@17.0.0"],
    dependencies_updated: [{ name: "rxjs", from: "7.8.0", to: "7.8.1" }],
    dev_dependencies_added: [],
    dev_dependencies_removed: [],
    dev_dependencies_updated: [],
    angular_version_before: "17.0.0",
    angular_version_after: "18.0.0",
    other_major_changes: [],
  },
  migration_list: ["migration-1", "migration-2"],
  forbidden_changes: [
    { file_path: "src/forbidden.ts", reason: "Uses deprecated API", risk_level: "high", suggestion: "Use new API instead" },
  ],
  changed_file_classifications: { "src/main.ts": "safe", "src/app.component.ts": "high_risk" },
  evidence_complete: true,
  artifact_ids: ["artifact-1", "artifact-2"],
  state_version: 2,
  event_sequence: 3,
  idempotent_replay: false,
  correlation_id: "corr-123",
};

const defaultProps = {
  runId: "run-1",
  stageId: "stage-1",
  sourceSandboxPath: "/sandbox/source",
  targetSandboxPath: "/sandbox/target",
  expectedStateVersion: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getTransformationEvidence).mockResolvedValue(mockEvidence as never);
});

function renderViewer(overrides: Record<string, unknown> = {}) {
  return render(<TransformationEvidenceViewer {...defaultProps} {...overrides} />);
}

describe("TransformationEvidenceViewer", () => {
  it("renders loading skeleton initially", () => {
    vi.mocked(getTransformationEvidence).mockReturnValue(new Promise(() => {}) as never);
    const { container } = renderViewer();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("renders empty state with Generate Evidence button when GET returns 404", async () => {
    vi.mocked(getTransformationEvidence).mockRejectedValue(new ApiClientError("Not found", 404, "GET", "/path"));
    renderViewer();
    expect(await screen.findByText("Generate Evidence")).toBeInTheDocument();
    expect(screen.getByText("No evidence has been generated yet.")).toBeInTheDocument();
  });

  it("renders failure state with error message on GET error", async () => {
    vi.mocked(getTransformationEvidence).mockRejectedValue(new Error("Network error"));
    renderViewer();
    expect(await screen.findByText("Network error")).toBeInTheDocument();
  });

  it("renders evidence with file list and summary bar after successful GET", async () => {
    renderViewer();
    expect(await screen.findByText("Transformation Evidence")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("LOW")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("src/main.ts")).toBeInTheDocument();
    expect(screen.getByText("src/app.component.ts")).toBeInTheDocument();
  });

  it("renders metadata with correlation_id, run_id, stage_id", async () => {
    renderViewer();
    expect(await screen.findByText("corr-123")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(screen.getByText("stage-1")).toBeInTheDocument();
  });

  it("calls generateTransformationEvidence on Generate button click and transitions to success", async () => {
    vi.mocked(getTransformationEvidence).mockRejectedValue(new ApiClientError("Not found", 404, "GET", "/path"));
    vi.mocked(generateTransformationEvidence).mockResolvedValue(mockEvidence as never);
    renderViewer();
    const btn = await screen.findByRole("button", { name: "Generate Evidence" });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(generateTransformationEvidence).toHaveBeenCalledWith("run-1", "stage-1", expect.objectContaining({
        expected_state_version: 2,
        source_sandbox_path: "/sandbox/source",
        target_sandbox_path: "/sandbox/target",
      }));
    });
    expect(await screen.findByText("LOW")).toBeInTheDocument();
  });

  it("shows failure state when generateTransformationEvidence fails", async () => {
    vi.mocked(getTransformationEvidence).mockRejectedValue(new ApiClientError("Not found", 404, "GET", "/path"));
    vi.mocked(generateTransformationEvidence).mockRejectedValue(new Error("Generation failed"));
    renderViewer();
    const btn = await screen.findByRole("button", { name: "Generate Evidence" });
    fireEvent.click(btn);
    expect(await screen.findByText("Generation failed")).toBeInTheDocument();
  });

  it("switches between diff, package, risk, and migrations tabs", async () => {
    renderViewer();
    await screen.findByText("src/main.ts");

    fireEvent.click(screen.getByText("Package Changes"));
    expect(screen.getByText("Dependencies")).toBeInTheDocument();
    expect(screen.getByText(/Added: 1/)).toBeInTheDocument();
    expect(screen.getByText(/Before: 17.0.0/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Risk Report"));
    expect(screen.getByText("src/forbidden.ts")).toBeInTheDocument();
    expect(screen.getByText("Uses deprecated API")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Migrations"));
    expect(screen.getByText("migration-1")).toBeInTheDocument();
    expect(screen.getByText("migration-2")).toBeInTheDocument();
  });

  it("filters files by risk classification via dropdown", async () => {
    renderViewer();
    await screen.findByText("src/main.ts");
    const select = screen.getByRole("combobox", { name: "Filter by risk classification" });
    fireEvent.change(select, { target: { value: "safe" } });
    expect(screen.getByText("src/main.ts")).toBeInTheDocument();
    expect(screen.queryByText("src/app.component.ts")).not.toBeInTheDocument();
  });

  it("shows forbidden changes in risk tab", async () => {
    renderViewer();
    await screen.findByText("Transformation Evidence");
    fireEvent.click(screen.getByText("Risk Report"));
    expect(screen.getByText("src/forbidden.ts")).toBeInTheDocument();
    expect(screen.getByText("Uses deprecated API")).toBeInTheDocument();
    expect(screen.getByText(/Suggestion:/)).toBeInTheDocument();
  });

  it("shows migration list in migrations tab", async () => {
    renderViewer();
    await screen.findByText("Transformation Evidence");
    fireEvent.click(screen.getByText("Migrations"));
    expect(screen.getByText("migration-1")).toBeInTheDocument();
    expect(screen.getByText("migration-2")).toBeInTheDocument();
  });

  it("renders clickable artifact links at the bottom", async () => {
    renderViewer();
    await screen.findByText("Transformation Evidence");
    const link1 = screen.getByText("artifact-1").closest("a");
    const link2 = screen.getByText("artifact-2").closest("a");
    expect(link1).toHaveAttribute("href", "/api/v1/artifacts/artifact-1");
    expect(link2).toHaveAttribute("href", "/api/v1/artifacts/artifact-2");
  });

  it("shows blocked state with block_reason when evidence_complete is false", async () => {
    const blocked = { ...mockEvidence, evidence_complete: false, block_reason: "Source sandbox modified" };
    vi.mocked(getTransformationEvidence).mockResolvedValue(blocked as never);
    renderViewer();
    expect(await screen.findByText("Source sandbox modified")).toBeInTheDocument();
  });

  it("shows idempotent replay badge when idempotent_replay is true", async () => {
    const replayEvidence = { ...mockEvidence, idempotent_replay: true };
    vi.mocked(getTransformationEvidence).mockResolvedValue(replayEvidence as never);
    renderViewer();
    expect(await screen.findByText("Idempotent replay")).toBeInTheDocument();
  });

  it("shows [Unknown — review required] label for unknown classified files", async () => {
    renderViewer();
    await screen.findByText("Transformation Evidence");
    expect(screen.getByText("[Unknown — review required]")).toBeInTheDocument();
  });

  it("shows high-risk filter warning when filter hides high-risk or sensitive items", async () => {
    renderViewer();
    await screen.findByText("src/main.ts");
    const select = screen.getByRole("combobox", { name: "Filter by risk classification" });
    fireEvent.change(select, { target: { value: "safe" } });
    expect(screen.getByText(/Filter hides 2 high-risk finding/)).toBeInTheDocument();
  });

  it("renders large diff banner and limits visible files when >50", async () => {
    const largeFiles = Array.from({ length: 60 }, (_, i) => ({
      file_path: `src/file${i}.ts`,
      change_type: "modified" as const,
      classification: "safe" as const,
      lines_added: 1,
      lines_removed: 0,
    }));
    const largeEvidence = {
      ...mockEvidence,
      total_files_changed: 60,
      diff_summary: {
        changed_files: largeFiles,
        files_by_classification: { safe: 60 },
      },
    };
    vi.mocked(getTransformationEvidence).mockResolvedValue(largeEvidence as never);
    renderViewer();
    expect(await screen.findByText(/Showing 50 of 60 files/)).toBeInTheDocument();
    expect(screen.getByText("src/file0.ts")).toBeInTheDocument();
    expect(screen.queryByText("src/file55.ts")).not.toBeInTheDocument();
  });

  it("renders reconnecting bar when connectionStatus is reconnecting", async () => {
    vi.mocked(getTransformationEvidence).mockReturnValue(new Promise(() => {}) as never);
    renderViewer({ connectionStatus: "reconnecting" });
    expect(await screen.findByText("Reconnecting to backend...")).toBeInTheDocument();
  });

  it("shows PASSED status pill for success state", async () => {
    renderViewer();
    expect(await screen.findByText("PASSED")).toBeInTheDocument();
  });

  it("shows empty text when no files match the risk filter", async () => {
    renderViewer();
    await screen.findByText("src/main.ts");
    const select = screen.getByRole("combobox", { name: "Filter by risk classification" });
    fireEvent.change(select, { target: { value: "nonexistent" } });
    expect(screen.getByText("No matching files")).toBeInTheDocument();
  });

  it("does not render artifact section when artifact_ids is empty", async () => {
    const noArtifacts = { ...mockEvidence, artifact_ids: [] };
    vi.mocked(getTransformationEvidence).mockResolvedValue(noArtifacts as never);
    renderViewer();
    await screen.findByText("Transformation Evidence");
    expect(screen.queryByText("Artifacts:")).not.toBeInTheDocument();
  });

  it("calls fetchEvidence again when connectionStatus changes to recovering", async () => {
    const { rerender } = renderViewer({ connectionStatus: "open" });
    await screen.findByText("PASSED");
    vi.mocked(getTransformationEvidence).mockClear();
    rerender(<TransformationEvidenceViewer {...defaultProps} connectionStatus="recovering" />);
    await waitFor(() => {
      expect(getTransformationEvidence).toHaveBeenCalledWith("run-1", "stage-1");
    });
  });

  it("shows stale state with Refresh button when GET returns 409", async () => {
    let fetchCount = 0;
    vi.mocked(getTransformationEvidence).mockImplementation(() => {
      fetchCount++;
      if (fetchCount === 1) return Promise.resolve(mockEvidence as never);
      return Promise.reject(new ApiClientError("Conflict", 409, "GET", "/path"));
    });
    const { rerender } = renderViewer({ connectionStatus: "open" });
    await screen.findByText("Transformation Evidence");
    rerender(<TransformationEvidenceViewer {...defaultProps} connectionStatus="recovering" />);
    expect(await screen.findByText("Evidence is stale — refresh")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });

  it("shows missing-artifact state with Retry button when evidence disappears", async () => {
    let fetchCount = 0;
    vi.mocked(getTransformationEvidence).mockImplementation(() => {
      fetchCount++;
      if (fetchCount === 1) return Promise.resolve(mockEvidence as never);
      return Promise.reject(new ApiClientError("Not found", 404, "GET", "/path"));
    });
    const { rerender } = renderViewer({ connectionStatus: "open" });
    await screen.findByText("Transformation Evidence");
    rerender(<TransformationEvidenceViewer {...defaultProps} connectionStatus="recovering" />);
    expect(await screen.findByText("Evidence artifacts not found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows binary classification badge in file list", async () => {
    const binaryEvidence = JSON.parse(JSON.stringify(mockEvidence));
    binaryEvidence.diff_summary.changed_files.push({
      file_path: "assets/logo.png", change_type: "modified", classification: "binary", lines_added: 0, lines_removed: 0, is_binary: true,
    });
    binaryEvidence.diff_summary.files_by_classification.binary = 1;
    binaryEvidence.total_files_changed = 6;
    vi.mocked(getTransformationEvidence).mockImplementation(() => Promise.resolve(binaryEvidence as never));
    renderViewer();
    await screen.findByText("assets/logo.png");
    expect(screen.getByText("binary")).toBeInTheDocument();
  });
});
