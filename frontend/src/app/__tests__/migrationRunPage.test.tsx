import { render, screen } from "@testing-library/react";
import MigrationRunPage from "@/app/migrations/[runId]/page";
import { getMockMigrationState } from "@/api/migrations";

vi.mock("@/api/migrations", () => ({ getMockMigrationState: vi.fn() }));
vi.mock("@/api/runs", () => ({ getAuthoritativeRunState: vi.fn() }));
vi.mock("@/components/RunDashboard", () => ({
  RunDashboard: ({ mode }: { mode?: string }) => <div data-testid="legacy-run-dashboard">Legacy dashboard ({mode})</div>,
}));
vi.mock("@/components/AuthoritativeRunDashboard", () => ({
  AuthoritativeRunDashboard: ({ runId }: { runId: string }) => <div data-testid="authoritative-run-dashboard">Authoritative {runId}</div>,
}));

describe("mock migration route", () => {
  it("uses the non-authoritative legacy shell for mock migration entries", async () => {
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

    expect(screen.getByTestId("legacy-run-dashboard")).toHaveTextContent("mock");
    expect(screen.getByRole("note")).toHaveTextContent(/demo data/i);
    expect(screen.queryByTestId("authoritative-run-dashboard")).not.toBeInTheDocument();
  });

  it("shows a retryable unavailable state when mock data cannot be loaded", async () => {
    vi.mocked(getMockMigrationState).mockRejectedValueOnce(new Error("offline"));
    render(await MigrationRunPage({ params: Promise.resolve({ runId: "mock-offline" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent(/demo migration data is unavailable/i);
    expect(screen.getByRole("link", { name: "Return to migrations" })).toHaveAttribute("href", "/");
  });
});
