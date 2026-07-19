import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getAuthoritativeRunState } from "@/api/runs";
import { LLM_EVENT_TYPES, useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

vi.mock("@/api/runs", () => ({ getAuthoritativeRunState: vi.fn().mockResolvedValue({ workflow_events: [], updated_at: "initial" }) }));
vi.mock("@/api/client", () => ({ getBackendBaseUrl: () => "http://backend" }));

class MockEventSource {
  static CLOSED = 2;
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (event: MessageEvent) => void>();
  constructor(public url: string) {}
  addEventListener(type: string, listener: (event: MessageEvent) => void) { this.listeners.set(type, listener); }
  removeEventListener(type: string) { this.listeners.delete(type); }
  close() { this.readyState = MockEventSource.CLOSED; }
  emit(type: string, payload: Record<string, unknown>) { this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(payload) })); }
}

const initialState = { workflow_events: [], updated_at: "initial" } as unknown as AuthoritativeRunStateDto;

describe("useAuthoritativeRun LLM SSE projection", () => {
  it("subscribes to LLM lifecycle and budget events and deduplicates replay", async () => {
    let source: MockEventSource | undefined;
    class CapturingEventSource extends MockEventSource { constructor(url: string) { super(url); source = this; } }
    vi.stubGlobal("EventSource", CapturingEventSource);
    const { result, unmount } = renderHook(() => useAuthoritativeRun("run-1", initialState));
    await act(async () => {});
    expect(LLM_EVENT_TYPES).toEqual(["LLM_INVOCATION_STARTED", "LLM_INVOCATION_COMPLETED", "LLM_INVOCATION_FAILED", "LLM_BUDGET_WARNING", "LLM_BUDGET_BLOCKED"]);
    act(() => { source!.emit("LLM_INVOCATION_STARTED", { event_id: "llm-event-1", event_type: "LLM_INVOCATION_STARTED", sequence: 1, occurred_at: "1" }); });
    act(() => { source!.emit("LLM_INVOCATION_STARTED", { event_id: "llm-event-1", event_type: "LLM_INVOCATION_STARTED", sequence: 1, occurred_at: "1" }); });
    expect(result.current.state.workflow_events).toHaveLength(1);
    expect(getAuthoritativeRunState).toHaveBeenCalled();
    unmount();
  });
});
