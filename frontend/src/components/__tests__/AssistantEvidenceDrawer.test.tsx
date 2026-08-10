import { fireEvent, render, screen } from "@testing-library/react";
import { AssistantEvidenceDrawer } from "@/components/AssistantEvidenceDrawer";

describe("AssistantEvidenceDrawer", () => {
  it("renders only the backend-validated citation subset", () => {
    render(<AssistantEvidenceDrawer citations={[{
      artifact_id: "artifact-a", checksum: "sha256:a", checksum_sha256: "sha256:a", label: "approved/a.json",
      excerpt_id: "excerpt-a", stage_key: "G02", locator: { kind: "line_range", value: "1-2" }, proof_label: "approved_evidence_supported",
    }]} />);

    expect(screen.getByRole("link", { name: "approved/a.json" })).toBeInTheDocument();
    expect(screen.getByText(/excerpt-a|sha256:a|line_range:1-2/)).toBeInTheDocument();
    expect(screen.queryByText("projection/b.json")).not.toBeInTheDocument();
    expect(screen.queryByText(/C:\\workspace|\/home\\/)).not.toBeInTheDocument();
  });

  it("uses a shared evidence title and keeps provenance details collapsed", () => {
    render(<AssistantEvidenceDrawer citations={[{
      artifact_id: "artifact-a", checksum: "sha256:a", label: "approved/a.json", stage_key: "G02", proof_label: "approved_evidence_supported",
    }]} />);
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "approved/a.json" })).toBeInTheDocument();
  });

  it("uses the registered artifact presentation title while keeping checksum and locator technical", () => {
    render(<AssistantEvidenceDrawer citations={[{
      artifact_id: "artifact-a", checksum: "sha256:a", label: "legacy-label.json", locator: { kind: "line_range", value: "1-2" },
    }]} artifacts={[{
      artifact_id: "artifact-a", run_id: "run-1", stage_id: "G02", artifact_type: "json", relative_path: "03_g02/package.json", created_at: "2026-01-01T00:00:00Z", checksum: "sha256:a",
    }]} />);
    expect(screen.getByRole("link", { name: "Source snapshot package" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "legacy-label.json" })).not.toBeInTheDocument();
    expect(screen.getByText(/line_range:1-2/)).not.toBeVisible();
    fireEvent.click(screen.getByText("Evidence"));
    expect(screen.getByText(/line_range:1-2/)).toBeInTheDocument();
  });
});
