import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AUTHORITATIVE_EVENT_TYPES, useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
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
    ]));
    act(() => {
      source!.emit("BASELINE_BACKEND_ANCHOR_CREATED", { event_id: "e3", event_type: "BASELINE_BACKEND_ANCHOR_CREATED", sequence: 3, occurred_at: "3" });
      source!.emit("BASELINE_FAILURES_FINGERPRINTED", { event_id: "e1", event_type: "BASELINE_FAILURES_FINGERPRINTED", sequence: 1, occurred_at: "1" });
      source!.emit("BASELINE_ROUTE_ANCHOR_CREATED", { event_id: "e2", event_type: "BASELINE_ROUTE_ANCHOR_CREATED", sequence: 2, occurred_at: "2" });
    });
    expect(result.current.state.workflow_events.map((event) => event.sequence)).toEqual([1, 2, 3]);
    unmount();
  });
});
