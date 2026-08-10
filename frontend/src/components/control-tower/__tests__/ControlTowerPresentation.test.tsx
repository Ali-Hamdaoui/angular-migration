import { fireEvent, render, screen } from "@testing-library/react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { StatusPresentation } from "@/presentation/status";
import { StatusPill } from "../../StatusPill";
import { PipelineSection } from "../PipelineSection";
import { TechnicalDetails } from "../TechnicalDetails";
import { WorkflowEventsSection } from "../WorkflowEventsSection";

const event = (event_type: string, sequence: number, payload: Record<string, unknown> = {}) => ({ event_id: `e-${sequence}`, run_id: "run", stage_id: null, event_type, occurred_at: `2026-07-27T10:0${sequence}:00Z`, sequence, payload });
const run = (workflow_events: AuthoritativeRunStateDto["workflow_events"]): AuthoritativeRunStateDto => ({ run_id: "run", status: "RUNNING", run_phase: "PREFLIGHT_SNAPSHOT", phase_status: "running", approval_status: "pending", repair_status: "not_required", state_version: 3, preflight_id: "p", source_path: "C:/source", target_output_path: "C:/target", graph_thread_id: "thread", created_at: "2026-07-27T10:00:00Z", updated_at: "2026-07-27T10:00:00Z", artifacts: [], workflow_events });

describe("control tower presentation state", () => {
  it("presents a created G11 gate as a warning with its human decision label", () => {
    const { container } = render(<StatusPill status="G11_CREATED" />);

    expect(screen.getByText("Repair validation acceptance required")).toBeInTheDocument();
    expect(screen.getByText("Repair validation acceptance required").closest("span")).toHaveAttribute("data-tone", "warning");
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector("svg")).not.toHaveAttribute("role");
  });

  it("renders an authoritative status presentation without remapping it", () => {
    const status: StatusPresentation = {
      label: "Evidence is authoritative",
      tone: "success",
      raw: "EVIDENCE_AUTHORITATIVE",
    };

    render(<StatusPill status={status} />);

    expect(screen.getByText("Evidence is authoritative").closest("span")).toHaveAttribute("data-tone", "success");
  });

  it("keeps unknown raw statuses neutral", () => {
    render(<StatusPill status="FUTURE_BACKEND_STATE" />);

    expect(screen.getByText("Future backend state").closest("span")).toHaveAttribute("data-tone", "neutral");
  });

  it("preserves the legacy value prop during migration", () => {
    render(<StatusPill value="WAITING_APPROVAL" />);

    expect(screen.getByText("Waiting for approval")).toBeInTheDocument();
  });

  it("uses a closed native disclosure for technical details", () => {
    render(
      <TechnicalDetails title="Technical details">
        <code>sha256:fixture</code>
      </TechnicalDetails>,
    );

    expect(screen.getByText("sha256:fixture")).not.toBeVisible();
    fireEvent.click(screen.getByText("Technical details"));
    expect(screen.getByText("sha256:fixture")).toBeVisible();
  });

  it("supports deliberately open technical details through native semantics", () => {
    render(
      <TechnicalDetails title="Run identifiers" open>
        <code>run-123</code>
      </TechnicalDetails>,
    );

    expect(screen.getByText("Run identifiers").closest("details")).toHaveAttribute("open");
    expect(screen.getByText("run-123")).toBeVisible();
  });

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
