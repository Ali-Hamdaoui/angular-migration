import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { StatusPresentation } from "@/presentation/status";
import { StatusPill } from "../../StatusPill";
import { ControlTowerHeader } from "../ControlTowerHeader";
import { PipelineSection } from "../PipelineSection";
import { ControlTowerSidebar } from "../ControlTowerSidebar";
import { TechnicalDetails } from "../TechnicalDetails";
import { WorkflowEventsSection } from "../WorkflowEventsSection";

const globalsCss = readFileSync("src/app/globals.css", "utf8");
const layoutCss = readFileSync("src/components/control-tower/ControlTowerLayout.module.css", "utf8");

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

  it("uses decorative Lucide icons while preserving navigation controls", () => {
    let selectedSection = "";
    let closeCount = 0;
    const { container } = render(
      <>
        <ControlTowerHeader
          runId="run"
          status="open"
          connectionLabel="Live"
          onMenu={() => undefined}
          state={run([])}
        />
        <ControlTowerSidebar
          activeSection="overview"
          open={false}
          onSelect={(section) => { selectedSection = section; }}
          onClose={() => { closeCount += 1; }}
        />
      </>,
    );

    expect(screen.getByRole("button", { name: "Open navigation" })).toHaveClass("controlTowerMenuButton");
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveClass("controlTowerClose");
    expect(screen.getByRole("button", { name: "Overview" }).querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));
    expect(selectedSection).toBe("pipeline");
    expect(closeCount).toBe(1);
    expect(container.querySelectorAll("svg").length).toBeGreaterThan(12);
    container.querySelectorAll("svg").forEach((icon) => {
      expect(icon).toHaveAttribute("aria-hidden", "true");
      expect(icon).not.toHaveAttribute("role");
    });
    expect(container.textContent).not.toMatch(/[Ãâ�☰×]/);
  });

  it("assigns connection colors only through explicit authoritative states", () => {
    expect(layoutCss).toMatch(/:global\(\.controlTowerConnection-open\)[^{]*\{[^}]*color:\s*var\(--color-success\)/);
    expect(layoutCss).toMatch(/:global\(\.controlTowerConnection-(?:loading|connecting)\)[\s\S]*:global\(\.controlTowerConnection-recovering\)[^{]*\{[^}]*color:\s*var\(--color-warning\)/);
    expect(layoutCss).toMatch(/:global\(\.controlTowerConnection-failed\)[^{]*\{[^}]*color:\s*var\(--color-danger\)/);
  });

  it("keeps drawer controls desktop-hidden and uses one below-768 mobile contract", () => {
    expect(layoutCss).toMatch(/:global\(\.controlTowerClose\),\s*:global\(\.controlTowerMenuButton\)\s*\{\s*display:\s*none/);
    expect(layoutCss).toContain("@media (max-width: 767px)");
    expect(layoutCss).not.toContain("max-width: 680px");
    expect(layoutCss).toMatch(/@media \(max-width: 420px\)[^{]*\{[\s\S]*:global\(\.controlTowerSummary\)/);
  });

  it("gives links a 44px wrapping interaction box", () => {
    expect(globalsCss).toMatch(/a\[href\]\s*\{[^}]*display:\s*inline-flex;[^}]*align-items:\s*center;[^}]*min-height:\s*44px;[^}]*max-width:\s*100%;[^}]*overflow-wrap:\s*anywhere/);
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
