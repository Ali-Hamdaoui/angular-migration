import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { getCommandLogSummary, getCommandLogs } from "@/api/commands";
import { LiveCommandLogViewer, StaticLogArtifactViewer } from "@/components/LogViewer";

vi.mock("@/api/commands", () => ({
  getCommandLogSummary: vi.fn(),
  getCommandLogs: vi.fn(),
}));

type Listener = (event: MessageEvent) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readonly listeners = new Map<string, Listener[]>();
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn(() => { this.readyState = 2; });

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: Listener) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }

  emit(name: string, data: Record<string, unknown>, lastEventId = "") {
    const event = { data: JSON.stringify(data), lastEventId } as MessageEvent;
    this.listeners.get(name)?.forEach((listener) => listener(event));
  }
}

describe("LiveCommandLogViewer", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.mocked(getCommandLogSummary).mockResolvedValue({
      execution_id: "exec-1", run_id: "run-1", total_chunks: 0,
      streams: { stdout: 0, stderr: 0, system: 0 }, first_sequence: null,
      last_sequence: null, finalized: false, finalized_at: null,
      truncated: { stdout: false, stderr: false }, redaction_applied: false,
    });
    vi.mocked(getCommandLogs).mockResolvedValue({ execution_id: "exec-1", run_id: "run-1", chunks: [], total: 0, offset: 0, limit: 100 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("connects in live mode, deduplicates sequences, and retains ordered output", async () => {
    render(<LiveCommandLogViewer runId="run-1" executionId="exec-1" maxLines={10} />);
    const source = FakeEventSource.instances[0];
    expect(source.url).toContain("http://127.0.0.1:8000/api/v1/runs/run-1/commands/exec-1/logs/stream?cursor=0");

    act(() => {
      source.onopen?.();
      source.emit("command_log", { sequence: 1, stream: "stdout", content: "first" });
      source.emit("command_log", { sequence: 1, stream: "stdout", content: "first" });
      source.emit("command_log", { sequence: 2, stream: "stderr", content: "second" });
    });

    expect(screen.getByText(/connected · sequence 2/)).toBeInTheDocument();
    expect(screen.getAllByText("first")).toHaveLength(1);
    expect(screen.getByText("second")).toBeInTheDocument();
  });

  it("reconnects from the latest confirmed cursor", async () => {
    vi.useFakeTimers();
    render(<LiveCommandLogViewer runId="run-1" executionId="exec-1" />);
    const first = FakeEventSource.instances[0];
    act(() => {
      first.emit("command_log", { sequence: 1, stream: "stdout", content: "one" });
      first.onerror?.();
      vi.advanceTimersByTime(500);
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1].url).toContain("http://127.0.0.1:8000/api/v1/runs/run-1/commands/exec-1/logs/stream?cursor=1");
  });

  it("keeps output visible and exposes artifact links after completion", async () => {
    render(<LiveCommandLogViewer runId="run-1" executionId="exec-1" executionStatus="failed" stdoutArtifactId="stdout-1" stderrArtifactId="stderr-1" />);
    const source = FakeEventSource.instances[0];
    act(() => {
      source.emit("command_log", { sequence: 1, stream: "stderr", content: "failure output" });
      source.emit("execution_complete", { status: "failed", last_sequence: 1 });
    });
    expect(screen.getByText("failure output")).toBeInTheDocument();
    expect(screen.getByText(/Final command status: failed/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open stdout artifact" })).toHaveAttribute("href", "http://127.0.0.1:8000/api/v1/artifacts/stdout-1");
  });

  it("filters locally without changing the global cursor", () => {
    render(<LiveCommandLogViewer runId="run-1" executionId="exec-1" />);
    const source = FakeEventSource.instances[0];
    act(() => {
      source.emit("command_log", { sequence: 1, stream: "stdout", content: "out" });
      source.emit("command_log", { sequence: 2, stream: "stderr", content: "err" });
    });
    fireEvent.click(screen.getByRole("button", { name: "stdout" }));
    expect(screen.getByText("out")).toBeInTheDocument();
    expect(screen.queryByText("err")).not.toBeInTheDocument();
    expect(screen.getByText(/sequence 2/)).toBeInTheDocument();
  });

  it("pauses consumption and resumes from the confirmed cursor", () => {
    render(<LiveCommandLogViewer runId="run-1" executionId="exec-1" />);
    const source = FakeEventSource.instances[0];
    act(() => source.emit("command_log", { sequence: 1, stream: "stdout", content: "one" }));
    fireEvent.click(screen.getByRole("button", { name: "Pause live output" }));
    expect(source.close).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Play live output" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Play live output" }));
    expect(FakeEventSource.instances.at(-1)?.url).toContain("cursor=1");
  });

  it("loads stored pages and filters output with user search", async () => {
    vi.mocked(getCommandLogs).mockResolvedValueOnce({
      execution_id: "exec-1", run_id: "run-1", total: 1, offset: 0, limit: 100,
      chunks: [{ sequence: 1, stream: "stdout", text: "stored match", redacted: false, truncated: true, created_at: "", byte_count: 12, character_count: 12 }],
    });
    render(<LiveCommandLogViewer runId="run-1" executionId="exec-1" />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search logs" }), { target: { value: "match" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Load stored logs" })); });
    expect(getCommandLogs).toHaveBeenCalledWith("run-1", "exec-1", { offset: 0, limit: 100 });
    expect(screen.getByText("stored match")).toBeInTheDocument();
    expect(screen.getByText(/Output truncated/)).toBeInTheDocument();
  });

  it("shows the correlation ID for a stream failure", () => {
    render(<LiveCommandLogViewer runId="run-1" executionId="exec-1" />);
    act(() => FakeEventSource.instances[0].emit("stream_error", { code: "LOG_STREAM_FAILED", message: "failed", correlation_id: "corr-1" }));
    expect(screen.getByText(/Correlation ID:/)).toHaveTextContent("corr-1");
  });

  it("renders static artifact content as escaped plain text", () => {
    const { container } = render(<StaticLogArtifactViewer content="<script>alert(1)</script>" />);
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });
});
