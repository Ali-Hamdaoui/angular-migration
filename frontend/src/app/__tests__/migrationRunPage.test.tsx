import { render, screen } from "@testing-library/react";
import MigrationRunPage from "@/app/migrations/[runId]/page";
import { getMockMigrationState } from "@/api/migrations";

vi.mock("@/api/migrations", () => ({ getMockMigrationState: vi.fn() }));
vi.mock("@/api/runs", () => ({ getAuthoritativeRunState: vi.fn() }));
vi.mock("@/components/RunDashboard", () => ({
  RunDashboard: () => <div data-testid="legacy-run-dashboard">Legacy dashboard</div>,
  adaptMockMigrationRun: (run: unknown) => run,
}));
vi.mock("@/components/AuthoritativeRunDashboard", () => ({
  AuthoritativeRunDashboard: ({ runId }: { runId: string }) => <div data-testid="authoritative-run-dashboard">Authoritative {runId}</div>,
}));

describe("mock migration route", () => {
  it("uses the Journey Command Center for mock migration entries", async () => {
    vi.mocked(getMockMigrationState).mockResolvedValue({
      run_id: "mock-run-angular-18-to-21",
      status: "WAITING",
      run_phase: "FEASIBILITY_PLANNING",
      phase_status: "waiting_approval",
      approval_status: "pending",
      repair_status: "not_required",
      artifacts: [],
      workflow_events: [],
    } as never);

    render(await MigrationRunPage({ params: Promise.resolve({ runId: "mock-run-angular-18-to-21" }) }));

    expect(screen.getByTestId("authoritative-run-dashboard")).toHaveTextContent("mock-run-angular-18-to-21");
    expect(screen.getByRole("note")).toHaveTextContent(/demo data/i);
    expect(screen.queryByTestId("legacy-run-dashboard")).not.toBeInTheDocument();
  });
});
