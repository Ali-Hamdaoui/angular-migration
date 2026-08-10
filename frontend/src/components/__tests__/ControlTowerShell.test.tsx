import { fireEvent, render, screen } from "@testing-library/react";
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

    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("link", { name: "Pipeline" }));
    expect(screen.getByRole("link", { name: "Pipeline" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "Stages" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Evidence" })).toHaveAttribute("href", "#evidence");
    expect(screen.getByRole("link", { name: "Diagnostics" })).toHaveAttribute("href", "#diagnostics");
  });

  it("does not expose authoritative controls for a demo run", () => {
    render(<ControlTowerShell run={mockMigrationRun} mode="mock" />);

    expect(screen.getByRole("note")).toHaveTextContent(/demo controls are unavailable/i);
    expect(screen.queryByRole("button", { name: /run governed smoke check/i })).not.toBeInTheDocument();
  });
});
