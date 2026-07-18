import { render, screen } from "@testing-library/react";
import { ControlTowerShell } from "@/components/ControlTowerShell";
import { mockMigrationRun } from "@/data/mockMigrationRun";

describe("ControlTowerShell", () => {
  it("renders backend-shaped status, stages, manual validation gates, and artifact preview metadata", () => {
    render(<ControlTowerShell run={mockMigrationRun} />);

    expect(screen.getByRole("heading", { name: /18\.x.*21\.x/ })).toBeInTheDocument();
    expect(screen.getAllByText("WAITING")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: /Angular 18\.x.*19\.x/ })).toBeInTheDocument();
    expect(screen.getByText("Phase")).toBeInTheDocument();
    expect(screen.getByText("Approval")).toBeInTheDocument();
    expect(screen.getByText("Repair")).toBeInTheDocument();
    expect(screen.getByText("manual validation required")).toBeInTheDocument();
    expect(screen.getByText("stages/angular-18-to-19/validation/build.log")).toBeInTheDocument();
    expect(screen.getByText("sha256:mock-command-log")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Diagnostics" })).toBeInTheDocument();
    expect(screen.getByText("llm.cost.total")).toBeInTheDocument();
    expect(screen.getAllByText("$0.000940").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("button", { name: "Preview" })).toHaveLength(mockMigrationRun.artifacts.length);
  });
});
