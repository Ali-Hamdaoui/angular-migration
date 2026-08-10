import { render, screen } from "@testing-library/react";
import { ControlTowerShell } from "@/components/ControlTowerShell";
import { mockMigrationRun } from "@/data/mockMigrationRun";

describe("ControlTowerShell", () => {
  it("renders human status labels alongside raw evidence and backend-shaped details", () => {
    render(<ControlTowerShell run={mockMigrationRun} />);

    expect(screen.getByRole("heading", { name: /18\.x.*21\.x/ })).toBeInTheDocument();
    expect(screen.getByText("Waiting")).toBeInTheDocument();
    expect(screen.getByText("WAITING")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Angular 18\.x.*19\.x/ })).toBeInTheDocument();
    expect(screen.getByText("Phase")).toBeInTheDocument();
    expect(screen.getByText("Approval")).toBeInTheDocument();
    expect(screen.getAllByText("Repair").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Manual validation required")).toBeInTheDocument();
    expect(screen.getByText("stages/angular-18-to-19/validation/build.log")).toBeInTheDocument();
    expect(screen.getByText("sha256:mock-command-log")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Diagnostics" })).toBeInTheDocument();
    expect(screen.getByText("llm.cost.total")).toBeInTheDocument();
    expect(screen.getAllByText("$0.000940").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("button", { name: "Preview" })).toHaveLength(mockMigrationRun.artifacts.length);
  });

  it("keeps the legacy shell's four primary destinations explicit", () => {
    render(<ControlTowerShell run={mockMigrationRun} />);

    expect(screen.getByRole("navigation", { name: "Run sections" })).toHaveTextContent("OverviewPipelineEvidenceDiagnostics");
  });
});
