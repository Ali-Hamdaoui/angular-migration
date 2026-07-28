import { fireEvent, render, screen } from "@testing-library/react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { PipelineSection } from "../PipelineSection";
import { WorkflowEventsSection } from "../WorkflowEventsSection";

const event = (event_type: string, sequence: number, payload: Record<string, unknown> = {}) => ({ event_id: `e-${sequence}`, run_id: "run", stage_id: null, event_type, occurred_at: `2026-07-27T10:0${sequence}:00Z`, sequence, payload });
const run = (workflow_events: AuthoritativeRunStateDto["workflow_events"]): AuthoritativeRunStateDto => ({ run_id: "run", status: "RUNNING", run_phase: "PREFLIGHT_SNAPSHOT", phase_status: "running", approval_status: "pending", repair_status: "not_required", state_version: 3, preflight_id: "p", source_path: "C:/source", target_output_path: "C:/target", graph_thread_id: "thread", created_at: "2026-07-27T10:00:00Z", updated_at: "2026-07-27T10:00:00Z", artifacts: [], workflow_events });

describe("control tower presentation state", () => {
  it("opens only the selected current stage and keeps logs collapsed", () => {
    render(<PipelineSection state={run([event("SOURCE_INTAKE_STARTED", 1)])} retryError={null} retrying={false} onRetry={() => undefined} />);
    expect(screen.getByRole("button", { name: /Source intake/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("heading", { name: "Command output" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Source snapshot/ }));
    expect(screen.getByRole("button", { name: /Source intake/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: /Source snapshot/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("filters and reverses events without changing the source array", () => {
    const events = [event("RUN_CREATED", 1), event("SNAPSHOT_CREATED", 2), event("RUN_FAILED", 3)];
    render(<WorkflowEventsSection events={events} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search events" }), { target: { value: "snapshot" } });
    expect(screen.getAllByText("SNAPSHOT_CREATED")).toHaveLength(2);
    expect(screen.queryByRole("listitem", { name: /RUN_CREATED/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search events" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Newest first" }));
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("RUN_FAILED");
    expect(events[0].sequence).toBe(1);
  });
});
