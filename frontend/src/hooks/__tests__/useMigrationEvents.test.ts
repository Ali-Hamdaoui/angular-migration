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

  emit(type: string, data: MigrationEventDto): void {
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

function makeEvent(type: MigrationEventDto["event_type"], id: string): MigrationEventDto {
  return {
    event_id: id,
    run_id: "mock-run-angular-18-to-21",
    stage_id: "angular-18-to-19",
    event_type: type,
    occurred_at: "2026-07-10T00:00:00Z",
    payload: { status: "RUNNING" },
  };
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

  it("appends stage and agent events to the events list", async () => {
    let capturedSource: MockEventSource | null = null;
    class CapturingEventSource extends MockEventSource {
      constructor(url: string) {
        super(url);
        capturedSource = this;
      }
    }

    const { result } = renderHook(() =>
      useMigrationEvents("mock-run-angular-18-to-21", CapturingEventSource as unknown as typeof EventSource),
    );

    await act(async () => {});
    expect(result.current.status).toBe("open");
    expect(capturedSource).not.toBeNull();

    const stageEvent = makeEvent("stage_state_changed", "evt-stage-1");
    const agentEvent = makeEvent("agent_state_changed", "evt-agent-1");

    act(() => {
      capturedSource!.emit("stage_state_changed", stageEvent);
      capturedSource!.emit("agent_state_changed", agentEvent);
    });

    expect(result.current.events).toEqual([stageEvent, agentEvent]);
  });

  it("transitions to reconnecting on error before close", async () => {
    let capturedSource: MockEventSource | null = null;
    class CapturingEventSource extends MockEventSource {
      constructor(url: string) {
        super(url);
        capturedSource = this;
      }
    }

    const { result } = renderHook(() =>
      useMigrationEvents("mock-run-angular-18-to-21", CapturingEventSource as unknown as typeof EventSource),
    );

    await act(async () => {});
    expect(result.current.status).toBe("open");

    act(() => capturedSource!.simulateError());
    expect(result.current.status).toBe("reconnecting" as ConnectionStatus);
  });

  it("transitions to closed when the source closes permanently", async () => {
    let capturedSource: MockEventSource | null = null;
    class CapturingEventSource extends MockEventSource {
      constructor(url: string) {
        super(url);
        capturedSource = this;
      }
    }

    const { result } = renderHook(() =>
      useMigrationEvents("mock-run-angular-18-to-21", CapturingEventSource as unknown as typeof EventSource),
    );

    await act(async () => {});

    act(() => capturedSource!.simulateClose());
    expect(result.current.status).toBe("closed");
  });

  it("closes the EventSource on unmount", async () => {
    let capturedSource: MockEventSource | null = null;
    class CapturingEventSource extends MockEventSource {
      constructor(url: string) {
        super(url);
        capturedSource = this;
      }
    }

    const { unmount } = renderHook(() =>
      useMigrationEvents("mock-run-angular-18-to-21", CapturingEventSource as unknown as typeof EventSource),
    );

    await act(async () => {});
    expect(capturedSource).not.toBeNull();
    expect(capturedSource!.readyState).toBe(MockEventSource.OPEN);

    unmount();
    expect(capturedSource!.readyState).toBe(MockEventSource.CLOSED);
  });
});
