import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getAuthoritativeRunState } from "@/api/runs";
import { AUTHORITATIVE_EVENT_TYPES, PARITY_BASELINE_EVENT_TYPES, useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

vi.mock("@/api/runs", () => ({ getAuthoritativeRunState: vi.fn().mockResolvedValue({ workflow_events: [], updated_at: "initial" }) }));
vi.mock("@/api/client", () => ({ getBackendBaseUrl: () => "http://backend" }));

type Listener = (event: MessageEvent) => void;
class MockEventSource {
  static CLOSED = 2;
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, Listener>();
  constructor(public url: string) {}
  addEventListener(type: string, listener: Listener) { this.listeners.set(type, listener); }
  removeEventListener(type: string) { this.listeners.delete(type); }
  close() { this.readyState = MockEventSource.CLOSED; }
  simulateError() { this.readyState = 1; this.onerror?.(); }
  emit(type: string, payload: Record<string, unknown>) { this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(payload) })); }
}

const initialState = { workflow_events: [], updated_at: "initial" } as unknown as AuthoritativeRunStateDto;

describe("useAuthoritativeRun Feature 13 SSE", () => {
  it("subscribes to and orders all Feature 13 replay events", async () => {
    let source: MockEventSource | undefined;
    class CapturingEventSource extends MockEventSource {
      constructor(url: string) { super(url); source = this; }
    }
    vi.stubGlobal("EventSource", CapturingEventSource);
    const { result, unmount } = renderHook(() => useAuthoritativeRun("run-1", initialState));
    await act(async () => {});
    expect(AUTHORITATIVE_EVENT_TYPES).toEqual(expect.arrayContaining([
      "BASELINE_FAILURES_FINGERPRINTED",
      "BASELINE_ROUTE_ANCHOR_CREATED",
      "BASELINE_BACKEND_ANCHOR_CREATED",
      "DISCOVERY_STARTED",
      "SCANNER_COMPLETED",
      "DISCOVERY_COMPLETED",
      "DISCOVERY_BLOCKED",
      "ANALYSIS_AGENT_STARTED",
      "ANALYSIS_REVIEWER_COMPLETED",
      "G04_CREATED",
      "G04_APPROVED",
      "COMPATIBILITY_RESOLUTION_STARTED",
      "COMPATIBILITY_RESOLUTION_COMPLETED",
      "COMPATIBILITY_RESOLUTION_BLOCKED",
      "G05_APPROVED",
      "COMMAND_SUCCEEDED",
      "COMMAND_FAILED",
    ]));
    act(() => {
      source!.emit("BASELINE_FAILURES_FINGERPRINTED", { event_id: "e1", event_type: "BASELINE_FAILURES_FINGERPRINTED", sequence: 1, occurred_at: "1" });
      source!.emit("BASELINE_ROUTE_ANCHOR_CREATED", { event_id: "e2", event_type: "BASELINE_ROUTE_ANCHOR_CREATED", sequence: 2, occurred_at: "2" });
      source!.emit("BASELINE_BACKEND_ANCHOR_CREATED", { event_id: "e3", event_type: "BASELINE_BACKEND_ANCHOR_CREATED", sequence: 3, occurred_at: "3" });
      source!.emit("COMPATIBILITY_RESOLUTION_STARTED", { event_id: "e4", event_type: "COMPATIBILITY_RESOLUTION_STARTED", sequence: 4, occurred_at: "4" });
    expect(PARITY_BASELINE_EVENT_TYPES).toEqual(["PARITY_BASELINE_STARTED", "PARITY_BASELINE_COMPLETED", "PARITY_BASELINE_BLOCKED"]);
    });
    expect(result.current.state.workflow_events.map((event) => event.sequence)).toEqual([1, 2, 3, 4]);
    unmount();
  });

it("refreshes authoritative state when the SSE connection reconnects", async () => {
  let source: MockEventSource | undefined;
  class CapturingEventSource extends MockEventSource { constructor(url: string) { super(url); source = this; } }
  vi.stubGlobal("EventSource", CapturingEventSource);
  vi.mocked(getAuthoritativeRunState).mockResolvedValue({ workflow_events: [{ event_id: "recovered-1", sequence: 1, occurred_at: "1" }], updated_at: "reconnected" } as never);
  const { result, unmount } = renderHook(() => useAuthoritativeRun("run-1", initialState));
  await act(async () => {});
  act(() => source!.simulateError());
  await act(async () => {});
  expect(getAuthoritativeRunState).toHaveBeenCalled();
  expect(result.current.status).toBe("open");
  expect(result.current.state.updated_at).toBe("reconnected");
  unmount();
});
});


  it("recovers the authoritative snapshot after an SSE sequence gap and ignores duplicates", async () => {
    let source: MockEventSource | undefined;
    class CapturingEventSource extends MockEventSource { constructor(url: string) { super(url); source = this; } }
    vi.stubGlobal("EventSource", CapturingEventSource);
    vi.mocked(getAuthoritativeRunState).mockResolvedValue({ workflow_events: [{ event_id: "e1", sequence: 1, occurred_at: "1" }], updated_at: "recovered" } as never);
    const { result, unmount } = renderHook(() => useAuthoritativeRun("run-1", initialState));
    await act(async () => {});
    act(() => { source!.emit("DISCOVERY_STARTED", { event_id: "e1", event_type: "DISCOVERY_STARTED", sequence: 1, occurred_at: "1" }); });
    act(() => { source!.emit("DISCOVERY_COMPLETED", { event_id: "e3", event_type: "DISCOVERY_COMPLETED", sequence: 3, occurred_at: "3" }); });
    await act(async () => {});
    expect(getAuthoritativeRunState).toHaveBeenCalled();
    expect(result.current.state.updated_at).toBe("recovered");
    unmount();
  });
