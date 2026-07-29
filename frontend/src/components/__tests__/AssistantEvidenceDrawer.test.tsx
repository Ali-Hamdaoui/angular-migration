import { render, screen } from "@testing-library/react";
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
});
