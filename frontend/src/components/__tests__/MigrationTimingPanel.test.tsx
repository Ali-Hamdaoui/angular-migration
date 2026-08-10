import { render, screen, waitFor } from "@testing-library/react";
import type { RunTimingDto } from "@/types/generated/api";
import { getAuthoritativeRunTiming } from "@/api/runs";
import { MigrationTimingPanel } from "@/components/MigrationTimingPanel";

vi.mock("@/api/runs", () => ({
  getAuthoritativeRunTiming: vi.fn(),
}));

const timing = {
  run_id: "run-timing-1",
  status: "COMPLETED",
  as_of: "2026-08-09T10:12:00Z",
  started_at: "2026-08-09T10:00:00Z",
  finished_at: "2026-08-09T10:12:00Z",
  total_duration_seconds: 720,
  total_measurement_status: "complete",
  activity: {
    llm: { duration_seconds: 60, measured_count: 2, unmeasured_count: 0, active_count: 0, measurement_status: "complete" },
    commands: { duration_seconds: 180, measured_count: 3, unmeasured_count: 0, active_count: 0, measurement_status: "complete" },
    human_approval_wait: { duration_seconds: 30, measured_count: 1, unmeasured_count: 0, active_count: 0, measurement_status: "complete" },
    repair: { duration_seconds: null, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" },
    validation: { duration_seconds: 90, measured_count: 1, unmeasured_count: 0, active_count: 0, measurement_status: "complete" },
    sealing: { duration_seconds: 15, measured_count: 1, unmeasured_count: 0, active_count: 0, measurement_status: "complete" },
  },
  phases: [
    { key: "PREFLIGHT_SNAPSHOT", label: "Preflight & snapshot", status: "completed", started_at: "2026-08-09T10:00:00Z", finished_at: "2026-08-09T10:02:00Z", duration_seconds: 120 },
  ],
  stages: [
    { key: "stage-a", label: "Angular 18 → 19", status: "completed", started_at: "2026-08-09T10:02:00Z", finished_at: "2026-08-09T10:08:00Z", duration_seconds: 360 },
    { key: "stage-b", label: "Angular 19 → 20", status: "not_started", started_at: null, finished_at: null, duration_seconds: null },
  ],
} satisfies RunTimingDto;

describe("MigrationTimingPanel", () => {
  beforeEach(() => vi.mocked(getAuthoritativeRunTiming).mockReset());

  it("renders wall-clock, cumulative activity, dynamic stages, and phases", async () => {
    vi.mocked(getAuthoritativeRunTiming).mockResolvedValue(timing);

    render(<MigrationTimingPanel runId="run-timing-1" refreshKey={4} />);

    expect(await screen.findByText("Total wall-clock")).toBeInTheDocument();
    expect(screen.getByText("12m 00s")).toBeInTheDocument();
    expect(screen.getByText("Cumulative activity — categories may overlap.")).toBeInTheDocument();
    expect(screen.getByText("Measured LLM execution")).toBeInTheDocument();
    expect(screen.getByText("Validation command activity")).toBeInTheDocument();
    expect(screen.getByText("Angular 18 → 19")).toBeInTheDocument();
    expect(screen.getByText("Angular 19 → 20")).toBeInTheDocument();
    expect(screen.getByText("Preflight & snapshot")).toBeInTheDocument();
    expect(screen.getByText("Not started.")).toBeInTheDocument();
  });

  it("shows partial evidence and unavailable values instead of fake zero seconds", async () => {
    vi.mocked(getAuthoritativeRunTiming).mockResolvedValue({
      ...timing,
      activity: {
        ...timing.activity,
        llm: { ...timing.activity.llm, duration_seconds: 5, unmeasured_count: 1, measurement_status: "partial" },
        commands: { ...timing.activity.commands, duration_seconds: null, measured_count: 0, measurement_status: "unavailable" },
      },
    });

    render(<MigrationTimingPanel runId="run-timing-1" />);

    expect(await screen.findByText(/1 invocation\(s\) lack timing/)).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText("0s")).not.toBeInTheDocument();
  });

  it("renders a running total as elapsed as of the server timestamp", async () => {
    vi.mocked(getAuthoritativeRunTiming).mockResolvedValue({
      ...timing,
      status: "RUNNING",
      finished_at: null,
      total_duration_seconds: 65,
      total_measurement_status: "running",
    });

    render(<MigrationTimingPanel runId="run-timing-1" />);

    expect(await screen.findByText("Elapsed as of")).toBeInTheDocument();
    expect(screen.getByText("1m 05s")).toBeInTheDocument();
  });

  it("keeps an API failure inside the panel", async () => {
    vi.mocked(getAuthoritativeRunTiming).mockResolvedValue(null as unknown as RunTimingDto);

    render(<MigrationTimingPanel runId="run-timing-1" />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Migration timing is temporarily unavailable"));
  });
});
