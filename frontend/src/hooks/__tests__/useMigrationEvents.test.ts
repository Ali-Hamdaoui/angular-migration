import { act, renderHook } from "@testing-library/react";
import { useMigrationEvents, type ConnectionStatus } from "@/hooks/useMigrationEvents";
import type { MigrationEventDto } from "@/types/generated/api";

type Listener = (event: { data: string }) => void;

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  readonly url: string;
  readyState: number = MockEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
    queueMicrotask(() => {
      this.readyState = MockEventSource.OPEN;
      this.onopen?.();
    });
  }

  addEventListener(type: string, listener: Listener): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: string, data: MigrationEventDto | Record<string, unknown>): void {
    const payload = new MessageEvent("message", { data: JSON.stringify(data) });
    this.listeners.get(type)?.forEach((fn) => fn(payload));
  }

  close(): void {
    this.readyState = MockEventSource.CLOSED;
  }

  simulateError(): void {
    this.readyState = MockEventSource.CONNECTING;
    this.onerror?.();
  }

  simulateClose(): void {
    this.readyState = MockEventSource.CLOSED;
    this.onerror?.();
  }
}

function makeEvent(type: MigrationEventDto["event_type"], id: string, sequence = 1): MigrationEventDto {
  return {
    event_id: id,
    run_id: "mock-run-angular-18-to-21",
    stage_id: "angular-18-to-19",
    event_type: type,
    occurred_at: "2026-07-10T00:00:00Z",
    sequence,
    payload: { status: "RUNNING" },
  };
}

function renderWithSource() {
  let capturedSource: MockEventSource | null = null;
  class CapturingEventSource extends MockEventSource {
    constructor(url: string) {
      super(url);
      capturedSource = this;
    }
  }
  const hook = renderHook(() =>
    useMigrationEvents("mock-run-angular-18-to-21", CapturingEventSource as unknown as typeof EventSource),
  );
  return { ...hook, get source() { return capturedSource; } };
}

describe("useMigrationEvents", () => {
  it("connects and transitions to open status", async () => {
    const { result } = renderHook(() =>
      useMigrationEvents("mock-run-angular-18-to-21", MockEventSource as unknown as typeof EventSource),
    );

    expect(result.current.status).toBe("connecting");
    await act(async () => {});
    expect(result.current.status).toBe("open");
  });

  it("appends ordered events and suppresses duplicates", async () => {
    const { result, source } = renderWithSource();
    await act(async () => {});

    const first = makeEvent("stage_state_changed", "evt-stage-1", 1);
    const duplicate = makeEvent("stage_state_changed", "evt-stage-1", 1);
    const second = makeEvent("agent_state_changed", "evt-agent-1", 2);

    act(() => {
      source!.emit("stage_state_changed", first);
      source!.emit("stage_state_changed", duplicate);
      source!.emit("agent_state_changed", second);
    });

    expect(result.current.events).toEqual([first, second]);
    expect(result.current.lastSequence).toBe(2);
  });

  it("signals recovery when a sequence gap is detected", async () => {
    const { result, source } = renderWithSource();
    await act(async () => {});

    act(() => {
      source!.emit("stage_state_changed", makeEvent("stage_state_changed", "evt-stage-1", 1));
      source!.emit("agent_state_changed", makeEvent("agent_state_changed", "evt-agent-3", 3));
    });

    expect(result.current.status).toBe("recovering" as ConnectionStatus);
    expect(result.current.recoveryRequired).toBe(true);
    expect(result.current.events).toHaveLength(1);

    act(() => result.current.clearRecoveryRequired());
    expect(result.current.recoveryRequired).toBe(false);
  });

  it("signals recovery when replay is unavailable", async () => {
    const { result, source } = renderWithSource();
    await act(async () => {});

    act(() => source!.emit("replay_unavailable", { recovery: "snapshot_required" }));

    expect(result.current.status).toBe("recovering");
    expect(result.current.recoveryRequired).toBe(true);
  });

  it("transitions to reconnecting on error before close", async () => {
    const { result, source } = renderWithSource();
    await act(async () => {});
    expect(result.current.status).toBe("open");

    act(() => source!.simulateError());
    expect(result.current.status).toBe("reconnecting" as ConnectionStatus);
  });

  it("transitions to closed when the source closes permanently", async () => {
    const { result, source } = renderWithSource();
    await act(async () => {});

    act(() => source!.simulateClose());
    expect(result.current.status).toBe("closed");
  });

  it("receives snapshot lifecycle events through SSE", async () => {
    const { result, source } = renderWithSource();
    await act(async () => {});

    const snapshotStarted = makeEvent("SNAPSHOT_STARTED", "evt-snapshot-1", 1);
    const snapshotCreated = makeEvent("SNAPSHOT_CREATED", "evt-snapshot-2", 2);

    act(() => {
      source!.emit("SNAPSHOT_STARTED", snapshotStarted);
      source!.emit("SNAPSHOT_CREATED", snapshotCreated);
    });

    expect(result.current.events).toEqual([snapshotStarted, snapshotCreated]);
    expect(result.current.lastSequence).toBe(2);
  });

  it("closes the EventSource on unmount", async () => {
    const { unmount, source } = renderWithSource();
    await act(async () => {});
    expect(source).not.toBeNull();
    expect(source!.readyState).toBe(MockEventSource.OPEN);

    unmount();
    expect(source!.readyState).toBe(MockEventSource.CLOSED);
  });
});
