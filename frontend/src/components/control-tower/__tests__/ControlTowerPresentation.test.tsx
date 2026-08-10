import { readFileSync } from "node:fs";
import { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";
import type { CurrentAction, RunWorkspaceProjection } from "@/presentation/currentAction";
import type { JourneyMilestone } from "@/presentation/runJourney";
import type { StatusPresentation } from "@/presentation/status";
import { presentArtifact } from "@/presentation/artifacts";
import { makeArtifact } from "@/test/authoritativeFixtures";
import { StatusPill } from "../../StatusPill";
import { CurrentActionCard } from "../CurrentActionCard";
import { ControlTowerHeader } from "../ControlTowerHeader";
import { OperatorOverview } from "../OperatorOverview";
import { PipelineSection } from "../PipelineSection";
import { RunJourneyStrip } from "../RunJourneyStrip";
import { ControlTowerSidebar } from "../ControlTowerSidebar";
import { TechnicalDetails } from "../TechnicalDetails";
import { WorkflowEventsSection } from "../WorkflowEventsSection";

const globalsCss = readFileSync("src/app/globals.css", "utf8");
const layoutCss = readFileSync("src/components/control-tower/ControlTowerLayout.module.css", "utf8");

const event = (event_type: string, sequence: number, payload: Record<string, unknown> = {}) => ({ event_id: `e-${sequence}`, run_id: "run", stage_id: null, event_type, occurred_at: `2026-07-27T10:0${sequence}:00Z`, sequence, payload });
const run = (workflow_events: AuthoritativeRunStateDto["workflow_events"]): AuthoritativeRunStateDto => ({ run_id: "run", status: "RUNNING", run_phase: "PREFLIGHT_SNAPSHOT", phase_status: "running", approval_status: "pending", repair_status: "not_required", state_version: 3, preflight_id: "p", source_path: "C:/source", target_output_path: "C:/target", graph_thread_id: "thread", created_at: "2026-07-27T10:00:00Z", updated_at: "2026-07-27T10:00:00Z", artifacts: [], workflow_events });

const journey: JourneyMilestone[] = [
  { key: "setup", label: "Setup", state: "complete" },
  { key: "readiness", label: "Readiness", state: "complete" },
  { key: "plan", label: "Migration plan", state: "complete" },
  { key: "20-to-21", label: "Angular 20 to 21", state: "blocked", stageId: "stage-20-21" },
  { key: "validate", label: "Validate", state: "not-reached" },
  { key: "complete", label: "Complete", state: "not-reached" },
];

const fullJourney: JourneyMilestone[] = [
  { key: "setup", label: "Setup", state: "complete" },
  { key: "readiness", label: "Readiness", state: "complete" },
  { key: "g01", label: "Production readiness", state: "complete" },
  { key: "baseline", label: "Baseline", state: "complete" },
  { key: "discovery", label: "Discovery", state: "complete" },
  { key: "feasibility", label: "Feasibility", state: "complete" },
  { key: "plan", label: "Migration plan", state: "complete" },
  { key: "18-to-19", label: "Angular 18 to 19", state: "complete" },
  { key: "19-to-20", label: "Angular 19 to 20", state: "complete" },
  { key: "20-to-21", label: "Angular 20 to 21", state: "blocked" },
  { key: "validate", label: "Validate", state: "not-reached" },
  { key: "complete", label: "Complete", state: "not-reached" },
];

const currentAuthority = {
  freshness: "current",
  navigation: "permitted",
} as const;

function PipelineNavigationHarness({ action }: { action: CurrentAction }) {
  const [focusStage, setFocusStage] = useState<JourneyMilestone["key"]>();
  return <>
    <CurrentActionCard action={action} onNavigate={(_section, stageKey) => setFocusStage(stageKey)} />
    <PipelineSection
      state={run([event("SOURCE_INTAKE_STARTED", 1), event("G03_CREATED", 2)])}
      retryError={null}
      retrying={false}
      onRetry={() => undefined}
      qualificationAvailable
      focusStage={focusStage}
    />
  </>;
}

function workspace(currentAction: CurrentAction): RunWorkspaceProjection {
  return {
    journey,
    currentAction,
    completed: "Setup, Readiness, Migration plan",
    now: currentAction.title,
    next: currentAction.kind === "complete" ? "No further milestone" : "Angular 20 to 21",
  };
}

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
    expect(container.querySelectorAll("svg").length).toBeGreaterThanOrEqual(9);
    expect(screen.getByRole("button", { name: "Overview" }).querySelector(".lucide-layout-dashboard")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pipeline" }).querySelector(".lucide-git-branch")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Evidence" }).querySelector(".lucide-folder-search")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Diagnostics" }).querySelector(".lucide-activity")).toBeInTheDocument();
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

  it("renders the full journey as a semantic status list", () => {
    render(<RunJourneyStrip journey={journey} />);

    const migrationJourney = screen.getByRole("list", { name: "Migration journey" });
    expect(within(migrationJourney).getByRole("listitem", { name: "Setup: Complete" })).toBeInTheDocument();
    expect(within(migrationJourney).getByRole("listitem", { name: "Angular 20 to 21: Blocked" })).toBeInTheDocument();
    expect(within(migrationJourney).getAllByText("Not reached")).toHaveLength(2);
  });

  it("provides a typed mobile Previous Current Next window and a full-journey disclosure", () => {
    render(<RunJourneyStrip journey={fullJourney} />);

    const mobileWindow = screen.getByLabelText("Current migration window");
    expect(within(mobileWindow).getByRole("listitem", { name: "Previous: Angular 19 to 20: Complete" })).toBeInTheDocument();
    expect(within(mobileWindow).getByRole("listitem", { name: "Current: Angular 20 to 21: Blocked" })).toBeInTheDocument();
    expect(within(mobileWindow).getByRole("listitem", { name: "Next: Validate: Not reached" })).toBeInTheDocument();

    fireEvent.click(screen.getByText("Show full migration journey"));
    expect(within(screen.getByLabelText("Full migration journey")).getAllByRole("listitem", { hidden: true })).toHaveLength(12);
    expect(layoutCss).toMatch(/@media \(max-width: 767px\)[^{]*\{[\s\S]*\.journeyDesktop\s*\{[^}]*display:\s*none/);
    expect(layoutCss).toMatch(/@media \(max-width: 767px\)[^{]*\{[\s\S]*\.journeyMobile\s*\{[^}]*display:\s*grid/);
  });

  it("uses a current-action control only for operator navigation", () => {
    const onNavigate = vi.fn();
    const action: CurrentAction = {
      kind: "blocked",
      title: "Transformation blocked",
      summary: "Repair revalidation needs attention.",
      consequence: "Inspect the authoritative blocker before continuing.",
      section: "pipeline",
      stageKey: "20-to-21",
      evidenceIds: ["failure-evidence"],
      rawSource: "REPAIR_REVALIDATION_FAILED",
      authority: currentAuthority,
    };
    render(<CurrentActionCard action={action} onNavigate={onNavigate} />);

    expect(screen.getByRole("heading", { name: "Transformation blocked" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View in pipeline" }));
    expect(onNavigate).toHaveBeenCalledWith("pipeline", "20-to-21");
  });

  it.each([
    ["blocked transformation", { kind: "blocked", title: "Transformation blocked", summary: "Repair revalidation needs attention.", section: "pipeline", stageKey: "20-to-21", evidenceIds: [], rawSource: "blocked", authority: currentAuthority }],
    ["running command", { kind: "running", title: "Migration command running", summary: "The backend is executing the current migration command.", section: "pipeline", stageKey: "20-to-21", evidenceIds: [], rawSource: "command:running", authority: currentAuthority }],
    ["verified completion", { kind: "complete", title: "Migration verified complete", summary: "The staged migration and final target verification are durably recorded.", section: "overview", stageKey: "complete", evidenceIds: [], rawSource: "verified", authority: currentAuthority }],
    ["no available data", { kind: "unavailable", title: "Current action unavailable", summary: "No current action can be confirmed.", section: "diagnostics", evidenceIds: [], rawSource: "unavailable", authority: currentAuthority }],
  ] as Array<[string, CurrentAction]>)("presents the %s state without raw event vocabulary", (_case, action) => {
    render(
      <OperatorOverview
        projection={workspace(action)}
        run={run([])}
        transformation={null}
        transformationStatus="disabled"
        artifacts={[]}
        onNavigate={() => undefined}
      />,
    );

    expect(screen.getByRole("heading", { name: action.title })).toBeInTheDocument();
    expect(screen.getByText(action.summary)).toBeInTheDocument();
    expect(screen.queryByText(action.rawSource)).not.toBeVisible();
  });

  it("keeps raw identifiers, counts, and projection versions in closed Technical details", () => {
    const action: CurrentAction = { kind: "running", title: "Work in progress", summary: "Confirmed work continues.", section: "pipeline", evidenceIds: [], rawSource: "RUNNING", authority: currentAuthority };
    const authoritativeRun = { ...run([]), artifacts: [makeArtifact({ run_id: "run" })] };
    render(
      <OperatorOverview
        projection={workspace(action)}
        run={authoritativeRun}
        transformation={{ continuation_id: "continuation-1", state_version: 31 } as TransformationProjection}
        transformationStatus="ready"
        artifacts={authoritativeRun.artifacts.map(presentArtifact)}
        onNavigate={() => undefined}
      />,
    );

    const details = screen.getByText("Technical details").closest("details") as HTMLElement;
    expect(details).not.toHaveAttribute("open");
    for (const value of ["run", "RUNNING", "3", "0 events", "1 artifact", "continuation-1", "31"]) {
      within(details).getAllByText(value).forEach((item) => expect(item).not.toBeVisible());
    }
  });

  it("disables navigation while authoritative records are refreshing", () => {
    const action: CurrentAction = {
      kind: "unavailable",
      title: "Refreshing operator evidence",
      summary: "Confirmed journey state remains visible while authoritative records are refreshed.",
      section: "diagnostics",
      evidenceIds: [],
      rawSource: "connection:recovering",
      authority: { freshness: "refreshing", navigation: "withheld" },
    };
    render(<CurrentActionCard action={action} onNavigate={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Waiting for authoritative refresh" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Open diagnostics" })).not.toBeInTheDocument();
  });

  it.each([
    ["G02 readiness", "readiness", "Source review & G02"],
    ["G03 baseline", "baseline", "Baseline qualification"],
    ["transformation target", "20-to-21", "G03 readiness"],
  ] as const)("maps %s action navigation to the available pipeline row", async (_case, stageKey, rowLabel) => {
    const action: CurrentAction = {
      kind: "gate",
      title: `${_case} action`,
      summary: "Review the authoritative stage.",
      section: "pipeline",
      stageKey,
      evidenceIds: [],
      rawSource: _case,
      authority: currentAuthority,
    };
    render(<PipelineNavigationHarness action={action} />);

    fireEvent.click(screen.getByRole("button", { name: "View in pipeline" }));

    await waitFor(() => expect(screen.getByRole("button", { name: new RegExp(rowLabel) })).toHaveAttribute("aria-expanded", "true"));
  });

  it("exposes the Pipeline action-required badge in the navigation control name", () => {
    render(
      <ControlTowerSidebar
        activeSection="overview"
        open={false}
        actionRequired
        onSelect={() => undefined}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: "Pipeline Action required" })).toBeInTheDocument();
  });
});
