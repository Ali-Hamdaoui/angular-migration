import { fireEvent, render, screen } from "@testing-library/react";
import { ArtifactPreviewPanel } from "@/components/ArtifactPreviewPanel";
import { StaticLogArtifactViewer } from "@/components/LogViewer";
import { MarkdownReportViewer } from "@/components/MarkdownReportViewer";
import { UnifiedDiffViewer } from "@/components/UnifiedDiffViewer";
import type { ArtifactRefDto } from "@/types/generated/api";

const diffContent = `diff --git a/src/app/app.component.ts b/src/app/app.component.ts
--- a/src/app/app.component.ts
+++ b/src/app/app.component.ts
@@ -1,3 +1,3 @@
-import { OldModule } from "old";
+import { NewModule } from "new";
 export class AppComponent {}`;

const artifact: ArtifactRefDto = {
  artifact_id: "artifact-repair-diff",
  run_id: "mock-run-angular-18-to-21",
  stage_id: "angular-18-to-19",
  artifact_type: "patch",
  relative_path: "repair_attempts/angular-18-to-19/attempt-001/repair.patch",
  created_at: "2026-07-10T00:02:00Z",
  checksum: "sha256:repair"
};

describe("artifact viewers", () => {
  it("bounds large command logs and highlights search matches", () => {
    const content = Array.from({ length: 25 }, (_, index) => index === 2 ? "ERROR failing build" : `line ${index + 1}`).join("\n");

    render(<StaticLogArtifactViewer content={content} search="error" maxLines={10} />);

    expect(screen.getByLabelText("Command log viewer")).toBeInTheDocument();
    expect(screen.getByText(/15 additional log lines/)).toBeInTheDocument();
    expect(screen.getByText(/ERROR failing build/)).toBeInTheDocument();
  });

  it("renders unified diff headers, hunks, additions, removals, and context", () => {
    render(<UnifiedDiffViewer content={diffContent} />);

    expect(screen.getByLabelText("Unified diff viewer")).toBeInTheDocument();
    expect(screen.getByText(/diff --git/)).toBeInTheDocument();
    expect(screen.getByText(/@@ -1,3 \+1,3 @@/)).toBeInTheDocument();
    expect(screen.getByText(/-import \{ OldModule \}/)).toBeInTheDocument();
    expect(screen.getByText(/\+import \{ NewModule \}/)).toBeInTheDocument();
    expect(screen.getByText(/export class AppComponent/)).toBeInTheDocument();
  });

  it("renders markdown without executing raw HTML or script tags", () => {
    const { container } = render(<MarkdownReportViewer content={'# Evidence Report\n- **Status** `passed`\n<script>alert(1)</script>'} />);

    expect(screen.getByRole("heading", { name: "Evidence Report" })).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("passed")).toBeInTheDocument();
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.innerHTML).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
  });

  it("loads artifact content on demand and shows metadata, producer, checksum, and attempt", async () => {
    const loadArtifact = vi.fn().mockResolvedValue({ artifact, content: diffContent, created_by: "artifact-service" });

    render(<ArtifactPreviewPanel artifact={artifact} loadArtifact={loadArtifact} />);
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByText("artifact-service")).toBeInTheDocument();
    expect(loadArtifact).toHaveBeenCalledWith("artifact-repair-diff");
    expect(screen.getByText("artifact-repair-diff")).toBeInTheDocument();
    expect(screen.getByText("patch")).toBeInTheDocument();
    expect(screen.getByText("angular-18-to-19")).toBeInTheDocument();
    expect(screen.getByText("attempt-001")).toBeInTheDocument();
    expect(screen.getByText("sha256:repair")).toBeInTheDocument();
    expect(screen.getByText(/\+import \{ NewModule \}/)).toBeInTheDocument();
  });
});
