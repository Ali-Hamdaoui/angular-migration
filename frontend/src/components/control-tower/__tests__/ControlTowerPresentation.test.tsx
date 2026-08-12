import { readFileSync } from "node:fs";
import { useState, type ComponentProps } from "react";
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

const pipelineJourney: JourneyMilestone[] = [
  { key: "setup", label: "Setup", state: "complete" },
  { key: "readiness", label: "Readiness", state: "action-required" },
  { key: "g01", label: "Production readiness", state: "complete" },
  { key: "baseline", label: "Baseline", state: "complete" },
  { key: "discovery", label: "Discovery", state: "not-reached" },
  { key: "feasibility", label: "Feasibility", state: "not-reached" },
  { key: "plan", label: "Migration plan", state: "not-reached" },
  { key: "18-to-19", label: "Angular 18 to 19", state: "not-reached" },
  { key: "19-to-20", label: "Angular 19 to 20", state: "not-reached" },
  { key: "20-to-21", label: "Angular 20 to 21", state: "not-reached" },
  { key: "validate", label: "Validate", state: "not-reached" },
  { key: "complete", label: "Complete", state: "not-reached" },
];

const pipelineGroups = {
  setup: "prepare",
  readiness: "prepare",
  g01: "prepare",
  baseline: "baseline",
  discovery: "understand",
  feasibility: "decide",
  plan: "decide",
  "18-to-19": "transform",
  "19-to-20": "transform",
  "20-to-21": "transform",
  validate: "validate",
  complete: "validate",
} as const;

function pipelineContent(items = pipelineJourney) {
  return items.map((milestone) => ({
    milestone,
    group: pipelineGroups[milestone.key],
    occurredAt: milestone.key === "readiness" ? "2026-07-27T10:02:00Z" : null,
    evidenceCount: milestone.key === "readiness" ? 2 : null,
    tabs: milestone.key === "readiness"
      ? [
          { id: "summary", label: "Summary", panel: <p>Review the immutable source snapshot.</p> },
          { id: "command", label: "Command output", panel: <pre>npm ci completed</pre> },
          { id: "evidence", label: "Evidence", panel: <p>Two registered artifacts</p> },
          { id: "review", label: "Review", panel: <button type="button">Approve source snapshot</button> },
        ]
      : [{ id: "summary", label: "Summary", panel: <p>{milestone.label} summary</p> }],
  }));
}

function pipelineProps(overrides: Record<string, unknown> = {}) {
  return {
    state: run([event("SOURCE_INTAKE_STARTED", 1), event("G03_CREATED", 2)]),
    retryError: null,
    retrying: false,
    onRetry: () => undefined,
    journey: pipelineJourney,
    stageContent: pipelineContent(),
    ...overrides,
  } as ComponentProps<typeof PipelineSection>;
}

const currentAuthority = {
  freshness: "current",
  navigation: "permitted",
} as const;

function PipelineNavigationHarness({ action }: { action: CurrentAction }) {
  const [focusStage, setFocusStage] = useState<JourneyMilestone["key"]>();
  return <>
    <CurrentActionCard action={action} onNavigate={(_section, stageKey) => setFocusStage(stageKey)} />
    <PipelineSection {...pipelineProps({ focusStage })} />
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

  it("switches the journey strip to the window pattern below the desktop strip width", () => {
    expect(layoutCss).toMatch(/@media \(max-width: 979px\)[^{]*\{[\s\S]*\.journeyDesktop\s*\{[^}]*display:\s*none/);
    expect(layoutCss).toMatch(/@media \(max-width: 979px\)[^{]*\{[\s\S]*\.journeyMobile\s*\{[^}]*display:\s*grid/);
    expect(layoutCss).toMatch(/\.journeyMilestone\[data-state="current"\] \.journeyMarker[^{]*\{[^}]*box-shadow:/);
  });

  it("animates the running action indicator with an accent border and honors reduced motion", () => {
    expect(layoutCss).toMatch(/\.currentActionCard\[data-kind="running"\][^{]*\{[^}]*border-color:\s*var\(--color-accent\)/);
    expect(layoutCss).toContain("@keyframes currentActionSpin");
    expect(layoutCss).toMatch(/@media \(prefers-reduced-motion: reduce\)[^{]*\{[\s\S]*\.currentActionCard\[data-kind="running"\] \.currentActionIcon svg\s*\{[^}]*animation:\s*none/);
  });

  it("gives links a 44px wrapping interaction box", () => {
    expect(globalsCss).toMatch(/a\[href\]\s*\{[^}]*display:\s*inline-flex;[^}]*align-items:\s*center;[^}]*min-height:\s*44px;[^}]*max-width:\s*100%;[^}]*overflow-wrap:\s*anywhere/);
  });

  it("renders all twelve milestones in the six semantic groups with exactly one row expanded", () => {
    render(<PipelineSection {...pipelineProps()} />);

    for (const group of ["Prepare", "Baseline", "Understand", "Decide", "Transform", "Validate"]) {
      expect(screen.getByRole("heading", { name: group })).toBeInTheDocument();
    }
    for (const milestone of pipelineJourney) {
      expect(screen.getByRole("button", { name: new RegExp(`^${milestone.label}:`, "i") })).toBeInTheDocument();
    }
    expect(screen.getAllByRole("button", { expanded: true })).toHaveLength(1);
    expect(screen.getByRole("button", { name: /^Readiness:/i })).toHaveAttribute("aria-expanded", "true");
  });

  it.each([
    ["action-required", "Waiting for approval"],
    ["blocked", "Blocked"],
  ] as const)("uses a warning tone for a %s pipeline summary", (state, label) => {
    const tonedJourney = pipelineJourney.map((milestone) => ({
      ...milestone,
      state: milestone.key === "readiness" ? state : milestone.state,
    }));
    render(<PipelineSection {...pipelineProps({ journey: tonedJourney, stageContent: pipelineContent(tonedJourney), focusStage: "readiness" })} />);

    expect(screen.getByText(label, { selector: "strong" })).toHaveAttribute("data-tone", "warning");
  });

  it("keeps an operator-selected completed row open until a new authoritative current key arrives", () => {
    const { rerender } = render(<PipelineSection {...pipelineProps()} />);

    fireEvent.click(screen.getByRole("button", { name: /^Baseline:/i }));
    expect(screen.getByRole("button", { name: /^Baseline:/i })).toHaveAttribute("aria-expanded", "true");

    rerender(<PipelineSection {...pipelineProps({ stageContent: pipelineContent().map((item) => ({ ...item })) })} />);
    expect(screen.getByRole("button", { name: /^Baseline:/i })).toHaveAttribute("aria-expanded", "true");

    const movedJourney = pipelineJourney.map((milestone) => ({
      ...milestone,
      state: milestone.key === "readiness" ? "complete" as const : milestone.key === "discovery" ? "current" as const : milestone.state,
    }));
    rerender(<PipelineSection {...pipelineProps({ journey: movedJourney, stageContent: pipelineContent(movedJourney) })} />);
    expect(screen.getByRole("button", { name: /^Discovery:/i })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("button", { expanded: true })).toHaveLength(1);
  });

  it("uses JourneyKey for the typed focus handoff", async () => {
    const { rerender } = render(<PipelineSection {...pipelineProps()} />);
    rerender(<PipelineSection {...pipelineProps({ focusStage: "plan" })} />);

    await waitFor(() => expect(screen.getByRole("button", { name: /^Migration plan:/i })).toHaveAttribute("aria-expanded", "true"));
  });

  it("implements linked roving tabs and mounts only the selected panel", () => {
    render(<PipelineSection {...pipelineProps()} />);

    const tablist = screen.getByRole("tablist", { name: "Readiness details" });
    const summary = within(tablist).getByRole("tab", { name: "Summary" });
    const command = within(tablist).getByRole("tab", { name: "Command output" });
    const evidence = within(tablist).getByRole("tab", { name: "Evidence" });
    const review = within(tablist).getByRole("tab", { name: "Review" });
    expect(summary).toHaveAttribute("aria-selected", "true");
    expect(summary).toHaveAttribute("tabindex", "0");
    expect(command).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", summary.id);
    expect(screen.getByText("Review the immutable source snapshot.")).toBeInTheDocument();
    expect(screen.queryByText("npm ci completed")).not.toBeInTheDocument();

    fireEvent.keyDown(summary, { key: "ArrowRight" });
    expect(command).toHaveFocus();
    expect(command).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("npm ci completed")).toBeInTheDocument();
    expect(screen.queryByText("Review the immutable source snapshot.")).not.toBeInTheDocument();

    fireEvent.keyDown(command, { key: "End" });
    expect(review).toHaveFocus();
    fireEvent.keyDown(review, { key: "ArrowRight" });
    expect(summary).toHaveFocus();
    fireEvent.keyDown(summary, { key: "ArrowLeft" });
    expect(review).toHaveFocus();
    fireEvent.keyDown(review, { key: "Home" });
    expect(summary).toHaveFocus();
    expect(evidence).toHaveAttribute("aria-controls");
  });

  it("omits unavailable command, evidence, and review tabs", () => {
    render(<PipelineSection {...pipelineProps({ focusStage: "baseline" })} />);

    expect(screen.getByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Command output" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Evidence" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Review" })).not.toBeInTheDocument();
  });

  it("filters and reverses events without changing the source array", () => {
    const events = [event("RUN_CREATED", 1), event("SNAPSHOT_CREATED", 2), event("RUN_FAILED", 3)];
    render(<WorkflowEventsSection events={events} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search events" }), { target: { value: "snapshot" } });
    expect(screen.getByText("Snapshot created", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("SNAPSHOT_CREATED", { selector: "code" })).not.toBeVisible();
    expect(screen.queryByRole("listitem", { name: /RUN_CREATED/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search events" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Newest first" }));
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("RUN_FAILED");
    expect(events[0].sequence).toBe(1);
  });

  it("renders the full journey as a semantic status list", () => {
    render(<RunJourneyStrip journey={journey} />);

    const migrationJourney = screen.getByRole("list", { name: "Migration journey" });
    expect(within(migrationJourney).getByRole("listitem", { name: "Setup: Completed" })).toBeInTheDocument();
    expect(within(migrationJourney).getByRole("listitem", { name: "Angular 20 to 21: Blocked" })).toBeInTheDocument();
    expect(within(migrationJourney).getAllByText("Not started")).toHaveLength(2);
  });

  it("provides a typed mobile Previous Current Next window and a full-journey disclosure", () => {
    render(<RunJourneyStrip journey={fullJourney} />);

    const mobileWindow = screen.getByLabelText("Current migration window");
    expect(within(mobileWindow).getByRole("listitem", { name: "Previous: Angular 19 to 20: Completed" })).toBeInTheDocument();
    expect(within(mobileWindow).getByRole("listitem", { name: "Current: Angular 20 to 21: Blocked" })).toBeInTheDocument();
    expect(within(mobileWindow).getByRole("listitem", { name: "Next: Validate: Not started" })).toBeInTheDocument();

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
    ["G02 readiness", "readiness", "Readiness"],
    ["G03 baseline", "baseline", "Baseline"],
    ["transformation target", "20-to-21", "Angular 20 to 21"],
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
