import { render, screen } from "@testing-library/react";
import { ApiClientError } from "@/api/client";
import { getAuthoritativeRunState } from "@/api/runs";
import HomePage from "@/app/page";

const dashboard = vi.fn(({ runId }: { runId: string }) => <div data-testid="authoritative-dashboard">Run {runId}<span>Transformation</span></div>);
vi.mock("@/api/runs", () => ({ getAuthoritativeRunState: vi.fn() }));
vi.mock("@/components/AuthoritativeRunDashboard", () => ({ AuthoritativeRunDashboard: (props: { runId: string }) => dashboard(props) }));
vi.mock("@/components/EnvironmentDiagnosticsPanel", () => ({ EnvironmentDiagnosticsPanel: () => null }));

const state = { run_id: "run-valid", workflow_events: [], updated_at: "now" };
function setUrl(value: string) { window.history.replaceState(null, "", value); }

describe("HomePage authoritative run restoration", () => {
  beforeEach(() => { window.localStorage.clear(); setUrl("/"); dashboard.mockClear(); vi.mocked(getAuthoritativeRunState).mockReset(); });

  it("restores a URL deep link and renders the cockpit", async () => {
    setUrl("/?run_id=run-valid"); vi.mocked(getAuthoritativeRunState).mockResolvedValue(state as never);
    render(<HomePage />);
    expect(await screen.findByTestId("authoritative-dashboard")).toHaveTextContent("run-valid");
    expect(screen.getByText("Transformation")).toBeInTheDocument();
    expect(getAuthoritativeRunState).toHaveBeenCalledWith("run-valid");
    expect(window.localStorage.getItem("amfa.activeRunId")).toBe("run-valid");
  });

  it("presents a clear landing choice when there is no active run", async () => {
    render(<HomePage />);
    expect(await screen.findByRole("heading", { name: "Start a migration" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a new migration" })).toHaveAttribute("href", "/migrations/new");
    expect(screen.getByText(/four .*steps/i)).toBeInTheDocument();
    expect(screen.getByText(/source stays read-only/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Resume active migration" })).not.toBeInTheDocument();
  });

  it("uses the last active run when the URL has no run id and updates the URL", async () => {
    window.localStorage.setItem("amfa.activeRunId", "run-last"); vi.mocked(getAuthoritativeRunState).mockResolvedValue({ ...state, run_id: "run-last" } as never);
    render(<HomePage />);
    expect(await screen.findByTestId("authoritative-dashboard")).toHaveTextContent("run-last");
    expect(window.location.search).toBe("?run_id=run-last");
  });

  it("gives the URL precedence over a different stored run", async () => {
    setUrl("/?run_id=run-url"); window.localStorage.setItem("amfa.activeRunId", "run-storage"); vi.mocked(getAuthoritativeRunState).mockResolvedValue({ ...state, run_id: "run-url" } as never);
    render(<HomePage />); await screen.findByTestId("authoritative-dashboard");
    expect(getAuthoritativeRunState).toHaveBeenCalledWith("run-url");
    expect(window.localStorage.getItem("amfa.activeRunId")).toBe("run-url");
  });

  it("clears an invalid run and returns to Prepare external migration", async () => {
    setUrl("/?run_id=run-missing"); window.localStorage.setItem("amfa.activeRunId", "run-missing"); vi.mocked(getAuthoritativeRunState).mockRejectedValue(new ApiClientError("missing", 404));
    render(<HomePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("requested migration run was not found");
    expect(screen.getByRole("heading", { name: "Start a migration" })).toBeInTheDocument();
    expect(window.localStorage.getItem("amfa.activeRunId")).toBeNull(); expect(window.location.search).toBe("");
  });

  it("preserves the active id and offers retry when the backend is unavailable", async () => {
    window.localStorage.setItem("amfa.activeRunId", "run-offline"); vi.mocked(getAuthoritativeRunState).mockRejectedValue(new ApiClientError("offline", 503));
    render(<HomePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("active run is preserved");
    expect(window.localStorage.getItem("amfa.activeRunId")).toBe("run-offline"); expect(screen.getByRole("button", { name: "Retry restoration" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resume active migration" })).toHaveAttribute("href", "/?run_id=run-offline");
  });
});
