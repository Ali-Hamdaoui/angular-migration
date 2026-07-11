import { render, screen } from "@testing-library/react";
import { ControlTowerShell } from "@/components/ControlTowerShell";
import { mockMigrationRun } from "@/data/mockMigrationRun";

describe("ControlTowerShell", () => {
  it("renders backend-shaped status, stages, and manual validation gates", () => {
    render(<ControlTowerShell run={mockMigrationRun} />);

    expect(screen.getByRole("heading", { name: /18\.x.*21\.x/ })).toBeInTheDocument();
    expect(screen.getAllByText("WAITING")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: /Angular 18\.x.*19\.x/ })).toBeInTheDocument();
    expect(screen.getByText("manual validation required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "http://127.0.0.1:8000/artifacts/artifact-mock-plan");
  });
});
