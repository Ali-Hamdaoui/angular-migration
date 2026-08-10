import { render, screen, waitFor } from "@testing-library/react";
import type { AuthoritativeRunStateDto, RunTimingDto } from "@/types/generated/api";
import { getLlmUsage } from "@/api/llm";
import { getAuthoritativeRunTiming } from "@/api/runs";
import { OperationalSummary } from "../OperationalSummary";

vi.mock("@/api/llm", () => ({ getLlmUsage: vi.fn() }));
vi.mock("@/api/runs", () => ({ getAuthoritativeRunTiming: vi.fn() }));

const run: AuthoritativeRunStateDto = {
  run_id: "run-1",
  status: "RUNNING",
  run_phase: "STAGED_MIGRATION",
  phase_status: "running",
  approval_status: "pending",
  repair_status: "not_required",
  state_version: 4,
  preflight_id: "preflight-1",
  source_path: "C:/source",
  target_output_path: "C:/target",
  graph_thread_id: "thread-1",
  created_at: "2026-08-10T10:00:00Z",
  updated_at: "2026-08-10T10:00:00Z",
  artifacts: [],
  workflow_events: [],
};

const usage = {
  run_id: "run-1",
  invocation_count: 2,
  llm_calls: 3,
  retry_calls: 1,
  usage_recorded_calls: 2,
  usage_unavailable_calls: 0,
  input_tokens: 100,
  output_tokens: 50,
  total_tokens: 150,
  input_cost_usd: 0.0001,
  output_cost_usd: 0.0002,
  total_cost_usd: 0.0003,
  pricing_versions: ["pricing-v1"],
  by_phase: [],
  by_stage: [],
  by_role: [],
  by_purpose: [],
  records: [],
};

const timing = {
  run_id: "run-1",
  status: "RUNNING",
  as_of: "2026-08-10T10:12:00Z",
  started_at: "2026-08-10T10:00:00Z",
  finished_at: null,
  total_duration_seconds: 65,
  total_measurement_status: "running" as const,
  activity: {
    llm: { duration_seconds: 60, measured_count: 2, unmeasured_count: 0, active_count: 0, measurement_status: "complete" },
    commands: { duration_seconds: 0, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" },
    human_approval_wait: { duration_seconds: 0, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" },
    repair: { duration_seconds: null, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" },
    validation: { duration_seconds: 0, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" },
    sealing: { duration_seconds: 0, measured_count: 0, unmeasured_count: 0, active_count: 0, measurement_status: "unavailable" },
  },
  phases: [],
  stages: [],
} satisfies RunTimingDto;

describe("OperationalSummary", () => {
  beforeEach(() => {
    vi.mocked(getLlmUsage).mockReset();
    vi.mocked(getAuthoritativeRunTiming).mockReset();
  });

  it("shows backend LLM calls, tokens, and running elapsed time", async () => {
    vi.mocked(getLlmUsage).mockResolvedValue(usage);
    vi.mocked(getAuthoritativeRunTiming).mockResolvedValue(timing);

    render(<OperationalSummary runId="run-1" run={run} />);

    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(screen.getByText("Total tokens")).toBeInTheDocument();
    expect(screen.getByText("1m 05s")).toBeInTheDocument();
    expect(screen.getByText("Elapsed as of")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Not finished")).toBeInTheDocument();
  });

  it("shows total wall-clock when the run is complete", async () => {
    vi.mocked(getLlmUsage).mockResolvedValue(usage);
    vi.mocked(getAuthoritativeRunTiming).mockResolvedValue({ ...timing, status: "COMPLETED", finished_at: "2026-08-10T10:12:00Z", total_duration_seconds: 720, total_measurement_status: "complete" });

    render(<OperationalSummary runId="run-1" run={run} />);

    expect(await screen.findByText("Total wall-clock")).toBeInTheDocument();
    expect(screen.getByText("12m 00s")).toBeInTheDocument();
    expect(screen.queryByText("Not finished")).not.toBeInTheDocument();
  });

  it("degrades honestly when the backend returns nothing", async () => {
    vi.mocked(getLlmUsage).mockRejectedValue(new Error("usage unavailable"));
    vi.mocked(getAuthoritativeRunTiming).mockRejectedValue(new Error("timing unavailable"));

    render(<OperationalSummary runId="run-1" run={run} />);

    await waitFor(() => {
      expect(screen.getByText("LLM usage not available.")).toBeInTheDocument();
      expect(screen.getByText("Migration timing not available.")).toBeInTheDocument();
    });
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
