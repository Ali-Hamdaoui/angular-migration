import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ArtifactRefDto } from "@/types/generated/api";
import { presentArtifact } from "@/presentation/artifacts";
import { EvidenceWorkspace } from "@/components/control-tower/EvidenceWorkspace";

const artifacts: ArtifactRefDto[] = [
  {
    artifact_id: "artifact-decision",
    run_id: "run-evidence",
    stage_id: "G02",
    artifact_type: "json",
    relative_path: "01_source_snapshot/G02/package.json",
    created_at: "2026-08-09T10:03:00Z",
    checksum: "sha256:decision",
  },
  {
    artifact_id: "artifact-command",
    run_id: "run-evidence",
    stage_id: "baseline",
    artifact_type: "command_log",
    relative_path: "02_baseline/commands/npm-test.stdout.log",
    created_at: "2026-08-09T10:01:00Z",
    checksum: "sha256:command",
  },
  {
    artifact_id: "artifact-unknown",
    run_id: "run-evidence",
    stage_id: null,
    artifact_type: "json",
    relative_path: "custom/strange-evidence.bin",
    created_at: "2026-08-09T10:02:00Z",
    checksum: "sha256:unknown",
  },
];

const presentations = artifacts.map(presentArtifact);

describe("EvidenceWorkspace", () => {
  it("searches human titles and raw metadata, and filters semantic categories", () => {
    render(<EvidenceWorkspace artifacts={presentations} />);

    expect(screen.getByRole("heading", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByText("Source snapshot package")).toBeInTheDocument();
    expect(screen.getByText("Strange evidence")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search evidence" }), { target: { value: "sha256:command" } });
    expect(screen.getByText("Npm test.stdout")).toBeInTheDocument();
    expect(screen.queryByText("Strange evidence")).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: "Evidence category" }), { target: { value: "decisions" } });
    fireEvent.change(screen.getByRole("searchbox", { name: "Search evidence" }), { target: { value: "" } });
    expect(screen.getByText("Source snapshot package")).toBeInTheDocument();
    expect(screen.queryByText("Npm test.stdout")).not.toBeInTheDocument();
  });

  it("selects an artifact, loads its preview, exposes provenance, and returns to the list", async () => {
    const loadArtifact = vi.fn().mockResolvedValue({ artifact: artifacts[0], content: '{"decision":"approved"}', created_by: "gate-service" });
    render(<EvidenceWorkspace artifacts={presentations} loadArtifact={loadArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: /Source snapshot package/i }));
    expect(screen.getByRole("button", { name: "Back to evidence" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Source snapshot package" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(loadArtifact).toHaveBeenCalledWith("artifact-decision"));
    expect(await screen.findByText("gate-service")).toBeInTheDocument();
    expect(screen.getByText("Provenance")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back to evidence" }));
    expect(screen.getByRole("searchbox", { name: "Search evidence" })).toBeInTheDocument();
  });

  it("reports an empty result set without inventing evidence", () => {
    render(<EvidenceWorkspace artifacts={presentations} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search evidence" }), { target: { value: "does-not-exist" } });
    expect(screen.getByText("No evidence matches these filters.")).toBeInTheDocument();
  });

  it("keeps a failed preview explicit and selectable for retry", async () => {
    const loadArtifact = vi.fn().mockRejectedValue(new Error("not available"));
    render(<EvidenceWorkspace artifacts={presentations} loadArtifact={loadArtifact} />);
    fireEvent.click(screen.getByRole("button", { name: /Source snapshot package/i }));
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Artifact preview is unavailable.");
    expect(screen.getByRole("button", { name: "Preview" })).toBeEnabled();
  });

  it("moves focus to the detail heading and restores it to the originating result", async () => {
    render(<EvidenceWorkspace artifacts={presentations} />);
    const result = screen.getByRole("button", { name: /Source snapshot package/i });
    fireEvent.click(result);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Source snapshot package" })).toHaveFocus());

    fireEvent.click(screen.getByRole("button", { name: "Back to evidence" }));
    expect(result).toHaveFocus();
  });
});
