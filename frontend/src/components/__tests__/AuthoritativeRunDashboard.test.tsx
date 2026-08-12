import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";
import { getG02Review } from "@/api/g02";
import { getBaselineSummary } from "@/api/baselineG03";
import { useAuthoritativeRun } from "@/hooks/useAuthoritativeRun";
import { useTransformation } from "@/hooks/useTransformation";
import { makeArtifact, makeAuthoritativeRun, makeEvent } from "@/test/authoritativeFixtures";
import type { AuthoritativeRunStateDto, BaselineAssessmentResponse, G02ReviewResponse } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";
import type { PipelineStageContent } from "@/components/control-tower/PipelineStageDetail";
import type { JourneyKey, JourneyMilestone } from "@/presentation/runJourney";

const pipelineRender = vi.fn();
type PipelineProps = {
  journey: JourneyMilestone[];
  stageContent: PipelineStageContent[];
  focusStage?: JourneyKey;
  expandedKey?: JourneyKey;
  onExpandedKeyChange?: (key: JourneyKey) => void;
};
let latestPipelineProps: PipelineProps | null = null;

vi.mock("@/hooks/useAuthoritativeRun", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useAuthoritativeRun")>("@/hooks/useAuthoritativeRun");
  return { ...actual, useAuthoritativeRun: vi.fn() };
});
vi.mock("@/hooks/useTransformation", () => ({ useTransformation: vi.fn() }));
vi.mock("@/api/g02", async () => {
  const actual = await vi.importActual<typeof import("@/api/g02")>("@/api/g02");
  return { ...actual, getG02Review: vi.fn() };
});
vi.mock("@/api/baselineG03", async () => {
  const actual = await vi.importActual<typeof import("@/api/baselineG03")>("@/api/baselineG03");
  return { ...actual, getBaselineSummary: vi.fn() };
});
vi.mock("@/components/control-tower/PipelineSection", () => ({
  PipelineSection: (props: PipelineProps) => {
    latestPipelineProps = props;
    pipelineRender(props);
    return (
      <section aria-label="Pipeline workspace">
        {props.expandedKey ?? props.focusStage ? `Focused stage: ${props.expandedKey ?? props.focusStage}` : "Pipeline workspace"}
        {props.stageContent.map((content) => (
          <button key={`inspect-${content.milestone.key}`} type="button" onClick={() => props.onExpandedKeyChange?.(content.milestone.key)}>
            Inspect {content.milestone.label}
          </button>
        ))}
        {props.stageContent.map((content) => (
          <span key={content.milestone.key} data-testid={`pipeline-${content.milestone.key}-tabs`}>
            {content.tabs.map((tab) => tab.label).join(",")}
          </span>
        ))}
      </section>
    );
  },
}));
vi.mock("@/components/LlmDiagnosticsPanel", () => ({ LlmDiagnosticsPanel: () => <p>Provider diagnostics</p> }));
vi.mock("@/components/MigrationTimingPanel", () => ({ MigrationTimingPanel: () => <p>timing-panel</p> }));
vi.mock("@/components/AssistantPanel", () => ({ AssistantDock: () => <button type="button">Open Assistant</button> }));
vi.mock("@/components/AuthoritativeRunCancellationPanel", () => ({ AuthoritativeRunCancellationPanel: () => <button type="button">Cancel run</button> }));

function transformationHook(overrides: Partial<ReturnType<typeof useTransformation>> = {}) {
  return {
    projection: null,
    executions: [],
    executionStatus: "idle" as const,
    status: "disabled" as const,
    refresh: vi.fn().mockResolvedValue(undefined),
    refreshError: null,
    loadError: null,
    ...overrides,
  };
}

function renderDashboard(
  run: AuthoritativeRunStateDto = makeAuthoritativeRun(),
  connection: ReturnType<typeof useAuthoritativeRun>["status"] = "open",
) {
  vi.mocked(useAuthoritativeRun).mockReturnValue({
    state: run,
    status: connection,
    error: null,
    refresh: vi.fn().mockResolvedValue(undefined),
  });
  return render(<AuthoritativeRunDashboard runId={run.run_id} initialState={run} />);
}

function pendingG06Run() {
  return makeAuthoritativeRun({
    state_version: 7,
    status: "WAITING_PLAN_APPROVAL",
    phase_status: "waiting_approval",
    approval_status: "pending",
    workflow_events: [
      makeEvent("RUN_CREATED", 1),
      makeEvent("G06_CREATED", 2, {
        payload: {
          gate_id: "G06",
          package_checksum: "sha256:g06",
          expected_state_version: 7,
          permitted_decisions: ["approved", "modification_requested", "rejected"],
        },
      }),
    ],
  });
}

function g02Review(packageChecksum: string, artifactId: string): G02ReviewResponse {
  return {
    run_id: "run-fixture",
    gate_id: "G02",
    gate_version: "g02-v1",
    status: "pending",
    decision: null,
    package: {
      run_id: "run-fixture",
      gate_id: "G02",
      gate_version: "g02-v1",
      state_version: 2,
      actor: "operator",
      policy_version: "source-snapshot-policy-v1",
      snapshot_id: "snapshot-1",
      source_fingerprint: "sha256:source",
      snapshot_fingerprint: "sha256:snapshot",
      artifact_set_checksum: "sha256:g02-artifacts",
      artifacts: [{
        artifact_id: artifactId,
        run_id: "run-fixture",
        stage_id: null,
        artifact_type: "json",
        relative_path: "global/g02/source-integrity.json",
        created_at: "2026-08-09T10:02:00Z",
        checksum: `sha256:${artifactId}`,
      }],
      integrity: {
        before_fingerprint: "sha256:source",
        after_snapshot_fingerprint: "sha256:source",
        snapshot_fingerprint: "sha256:snapshot",
        manifest_checksum: "sha256:manifest",
        policy_version: "source-snapshot-policy-v1",
        source_read_only_verified: true,
        status: "verified",
      },
      package_checksum: packageChecksum,
    },
    baseline_input_boundary: null,
    state_version: 2,
    event_sequence: 2,
    idempotent_replay: false,
    stale_reason: null,
    comment: null,
  };
}

function g03Assessment(packageChecksum: string, artifactId: string): BaselineAssessmentResponse {
  return {
    run_id: "run-fixture",
    assessment_id: "assessment-1",
    status: "qualified",
    policy: "strict_clean",
    policy_version: "baseline-policy-v1",
    blockers: [],
    warnings: [],
    known_failures: [],
    evidence_confidence: {},
    evidence_set_checksum: "sha256:g03-evidence",
    sandbox_fingerprint: "sha256:sandbox",
    execution_profile_checksum: "sha256:profile",
    package_checksum: packageChecksum,
    artifact_ids: [artifactId],
    state_version: 4,
    event_sequence: 4,
    g03_decision: null,
    stale_reason: null,
    idempotent_replay: false,
  };
}

function gatePackageRun(key: "readiness" | "baseline"): AuthoritativeRunStateDto {
  const g02Events = [
    makeEvent("RUN_CREATED", 1),
    makeEvent("G02_CREATED", 2, { payload: { snapshot_id: "snapshot-1", package_checksum: "sha256:g02-package" } }),
  ];
  if (key === "readiness") {
    return makeAuthoritativeRun({
      workflow_events: g02Events,
      artifacts: [makeArtifact({ artifact_id: "g02-package-artifact", relative_path: "global/g02/source-integrity.json" })],
    });
  }
  return makeAuthoritativeRun({
    state_version: 4,
    workflow_events: [
      ...g02Events,
      makeEvent("G02_APPROVED", 3),
      makeEvent("BASELINE_INSTALL_SUCCEEDED", 4),
      makeEvent("G03_CREATED", 5, { payload: { package_checksum: "sha256:g03-package", evidence_set_checksum: "sha256:g03-evidence" } }),
    ],
    artifacts: [makeArtifact({ artifact_id: "g03-package-artifact", relative_path: "global/g03/baseline-assessment.json" })],
  });
}

function reviewPanelFor(key: "readiness" | "baseline") {
  return latestPipelineProps?.stageContent
    .find((content) => content.milestone.key === key)
    ?.tabs.find((tab) => tab.id === "review")
    ?.panel;
}

function blockedTransformation(runId: string): TransformationProjection {
  return {
    run_id: runId,
    continuation_id: "continuation-1",
    stage_id: "stage-20-21",
    status: "blocked",
    current_node: "stage_transformation",
    state_version: 9,
    stage_status: "blocked",
    source_version: "20",
    target_version: "21",
    checkpoint_kind: null,
    workspace_fingerprint: "sha256:workspace",
    active_gate: null,
    active_gate_package_checksum: null,
    active_command_id: null,
    active_command_status: null,
    active_prompt_id: null,
    active_prompt_checksum: null,
    active_prompt_text: null,
    active_prompt_options: [],
    active_prompt_explanation: null,
    repair_attempt_id: null,
    repair_attempt_number: null,
    repair_status: null,
    repair_risk_level: null,
    repair_proposal_checksum: null,
    repair_review_checksum: null,
    repair_proposal_id: null,
    repair_base_checksum: null,
    repair_safe_diff: null,
    repair_review: null,
    repair_rationale: [],
    repair_apply_checksum: null,
    repair_validation_checksum: null,
    workflow_step: "stage_transformation",
    active_command_phase: null,
    stage_start_fingerprint: "sha256:workspace",
    repair_contract: null,
    dependency_operation: null,
    completed_transition_phases: [],
    repair_verification: null,
    dependency_closure: null,
    validation_results: {},
    active_error: { code: "POLICY_BLOCKED", message: "Policy blocked the stage." },
    historical_diagnostics: [],
    route_stages: [],
    sealed_chain_hash: null,
    last_error_code: null,
    last_error_message: null,
    runtime_profile_binding: null,
    cancel_requested_at: null,
  };
}

describe("AuthoritativeRunDashboard", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    latestPipelineProps = null;
    vi.mocked(useTransformation).mockReturnValue(transformationHook());
  });

  it("exposes exactly the four Journey Command Center destinations", () => {
    renderDashboard();
    const navigation = screen.getByRole("navigation", { name: "Run sections" });

    expect(within(navigation).getByRole("button", { name: "Overview" })).toBeInTheDocument();
    expect(within(navigation).getByRole("button", { name: "Pipeline" })).toBeInTheDocument();
    expect(within(navigation).getByRole("button", { name: "Evidence" })).toBeInTheDocument();
    expect(within(navigation).getByRole("button", { name: "Diagnostics" })).toBeInTheDocument();
    expect(within(navigation).getAllByRole("button")).toHaveLength(4);
    expect(screen.queryByRole("button", { name: "Transformation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "LLM Diagnostics" })).not.toBeInTheDocument();
  });

  it("keeps dev timing evidence in the Diagnostics destination", () => {
    renderDashboard();

    fireEvent.click(screen.getByRole("button", { name: "Diagnostics" }));

    expect(screen.getByText("timing-panel")).toBeInTheDocument();
  });

  it("owns exactly one authoritative run hook and one disabled transformation hook", () => {
    const run = makeAuthoritativeRun({
      workflow_events: [makeEvent("RUN_CREATED", 1), makeEvent("NOT_TRANSFORMATION_CONTINUATION_CREATED", 99)],
    });

    renderDashboard(run);

    expect(useAuthoritativeRun).toHaveBeenCalledOnce();
    expect(useTransformation).toHaveBeenCalledOnce();
    expect(useTransformation).toHaveBeenCalledWith(run.run_id, { enabled: false, refreshKey: 0 });
  });

  it("enables transformation only from staged phase or exact transformation event membership", () => {
    const run = makeAuthoritativeRun({
      workflow_events: [
        makeEvent("RUN_CREATED", 1),
        makeEvent("G07_CREATED", 4),
        makeEvent("TRANSFORMATION_CONTINUATION_WAITING", 7),
        makeEvent("G07_CREATED_LOOKALIKE", 99),
      ],
    });

    renderDashboard(run);

    expect(useTransformation).toHaveBeenCalledWith(run.run_id, { enabled: true, refreshKey: 7 });
  });

  it("enables transformation for the staged-migration phase without guessed events", () => {
    const run = makeAuthoritativeRun({ run_phase: "STAGED_MIGRATION" });

    renderDashboard(run);

    expect(useTransformation).toHaveBeenCalledWith(run.run_id, { enabled: true, refreshKey: 0 });
  });

  it("highlights Pipeline for an action without changing the operator's active destination", () => {
    renderDashboard(pendingG06Run());
    const pipeline = screen.getByRole("button", { name: "Pipeline Action required" });

    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(pipeline).toHaveAttribute("data-action-required", "true");
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));

    expect(screen.getByRole("button", { name: "Evidence" })).toHaveAttribute("aria-current", "page");
    expect(pipeline).not.toHaveAttribute("aria-current");
  });

  it("navigates and focuses a stage only after the operator uses the current-action link", () => {
    renderDashboard(pendingG06Run());

    fireEvent.click(screen.getByRole("button", { name: "View in pipeline" }));

    expect(screen.getByRole("button", { name: "Pipeline Action required" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Pipeline workspace")).toHaveTextContent("Focused stage: plan");
  });

  it("mounts feature workspaces only for the active destination", () => {
    renderDashboard();

    expect(screen.queryByLabelText("Pipeline workspace")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));
    expect(screen.getByLabelText("Pipeline workspace")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));
    expect(screen.queryByLabelText("Pipeline workspace")).not.toBeInTheDocument();
  });

  it("persists the operator-expanded journey key across Pipeline unmount and remount", () => {
    renderDashboard(pendingG06Run());
    fireEvent.click(screen.getByRole("button", { name: "Pipeline Action required" }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect Baseline" }));
    expect(screen.getByLabelText("Pipeline workspace")).toHaveTextContent("Focused stage: baseline");

    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));
    expect(screen.queryByLabelText("Pipeline workspace")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pipeline Action required" }));

    expect(screen.getByLabelText("Pipeline workspace")).toHaveTextContent("Focused stage: baseline");
  });

  it.each([
    ["pending", false],
    ["terminal", true],
  ])("keeps exact G02-G06 package evidence in the Pipeline for %s gates", async (_case, terminal) => {
    const scenarios: Array<{
      key: JourneyKey;
      artifactId: string;
      events: AuthoritativeRunStateDto["workflow_events"];
    }> = [
      {
        key: "readiness",
        artifactId: "g02-package-artifact",
        events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G02_CREATED", 2, { payload: { snapshot_id: "snapshot-1", package_checksum: "sha256:g02-package" } }),
          ...(terminal ? [makeEvent("G02_APPROVED", 3, { payload: { package_checksum: "sha256:g02-package", decision: "approved" } })] : []),
        ],
      },
      {
        key: "baseline",
        artifactId: "g03-package-artifact",
        events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G02_CREATED", 2),
          makeEvent("G02_APPROVED", 3),
          makeEvent("G03_CREATED", 4, { payload: { package_checksum: "sha256:g03-package", evidence_set_checksum: "sha256:g03-evidence" } }),
          ...(terminal ? [makeEvent("G03_REJECTED", 5, { payload: { package_checksum: "sha256:g03-package", decision: "rejected" } })] : []),
        ],
      },
      {
        key: "discovery",
        artifactId: "g04-created-artifact",
        events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("G04_CREATED", 2, { payload: { artifact_ids: ["g04-created-artifact"], artifact_set_checksum: "sha256:g04-set", package_checksum: "sha256:g04-package" } }),
          ...(terminal ? [makeEvent("G04_APPROVED", 3)] : []),
        ],
      },
      {
        key: "feasibility",
        artifactId: "g05-resolution-artifact",
        events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("COMPATIBILITY_RESOLUTION_COMPLETED", 2, { payload: { status: "supported", artifact_ids: ["g05-resolution-artifact"] } }),
          makeEvent("G05_CREATED", 3, { payload: { package_checksum: "sha256:g05-package", expires_at: "2026-08-10T12:00:00Z" } }),
          ...(terminal ? [makeEvent("G05_APPROVED", 4, { payload: { decision: "approve", package_checksum: "sha256:g05-package" } })] : []),
        ],
      },
      {
        key: "plan",
        artifactId: "g06-review-artifact",
        events: [
          makeEvent("RUN_CREATED", 1),
          makeEvent("MIGRATION_PLAN_CREATED", 2, { payload: { plan_id: "plan-1", artifact_ids: ["g06-plan-artifact"] } }),
          makeEvent("PLANNING_AGENT_COMPLETED", 3, { payload: { artifact_ids: ["g06-review-artifact"], plan_version: "plan-v1" } }),
          makeEvent("G06_CREATED", 4, { payload: { package_checksum: "sha256:g06-package", artifact_set_checksum: "sha256:g06-set" } }),
          ...(terminal ? [makeEvent("G06_REJECTED", 5, { payload: { package_checksum: "sha256:g06-package", plan_version: "plan-v1", decision: "reject" } })] : []),
        ],
      },
    ];

    for (const scenario of scenarios) {
      vi.mocked(getG02Review).mockResolvedValue(g02Review("sha256:g02-package", "g02-package-artifact"));
      vi.mocked(getBaselineSummary).mockResolvedValue(g03Assessment("sha256:g03-package", "g03-package-artifact"));
      const artifactIds = scenario.key === "plan" ? ["g06-plan-artifact", scenario.artifactId] : [scenario.artifactId];
      const run = makeAuthoritativeRun({
        workflow_events: scenario.events,
        artifacts: [
          ...artifactIds.map((artifactId) => makeArtifact({ artifact_id: artifactId, relative_path: `global/${artifactId}.json` })),
          makeArtifact({ artifact_id: `decoy-${scenario.key}`, relative_path: `global/decoy-${scenario.key}.json` }),
        ],
      });
      const view = renderDashboard(run);
      fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));

      await waitFor(() => expect(latestPipelineProps?.stageContent.find((content) => content.milestone.key === scenario.key)?.evidenceCount).toBe(artifactIds.length));
      const stage = latestPipelineProps?.stageContent.find((content) => content.milestone.key === scenario.key);
      const evidence = stage?.tabs.find((tab) => tab.id === "evidence");
      expect(evidence).toBeDefined();
      const evidenceView = render(<>{evidence?.panel}</>);
      for (const artifactId of artifactIds) {
        expect(evidenceView.container.querySelector(`a[href$="/${artifactId}"]`)).not.toBeNull();
      }
      expect(evidenceView.container.querySelector(`a[href$="/decoy-${scenario.key}"]`)).toBeNull();
      evidenceView.unmount();
      view.unmount();
    }
  });

  it("withholds a prior run's loaded G02 package while the next run package is unresolved", async () => {
    const firstRun = makeAuthoritativeRun({
      workflow_events: [
        makeEvent("RUN_CREATED", 1),
        makeEvent("G02_CREATED", 2, { payload: { snapshot_id: "snapshot-1", package_checksum: "sha256:g02-package" } }),
      ],
      artifacts: [makeArtifact({ artifact_id: "g02-package-artifact", relative_path: "global/g02/old-run.json" })],
    });
    vi.mocked(getG02Review).mockResolvedValueOnce(g02Review("sha256:g02-package", "g02-package-artifact"));
    const view = renderDashboard(firstRun);
    fireEvent.click(screen.getByRole("button", { name: "Pipeline" }));
    await waitFor(() => expect(latestPipelineProps?.stageContent.find((content) => content.milestone.key === "readiness")?.evidenceCount).toBe(1));

    vi.mocked(getG02Review).mockImplementationOnce(() => new Promise(() => undefined));
    const nextRun = makeAuthoritativeRun({
      run_id: "run-2",
      workflow_events: [
        makeEvent("RUN_CREATED", 1, { run_id: "run-2" }),
        makeEvent("G02_CREATED", 2, { run_id: "run-2", payload: { snapshot_id: "snapshot-2", package_checksum: "sha256:g02-package-2" } }),
      ],
      artifacts: [],
    });
    vi.mocked(useAuthoritativeRun).mockReturnValue({ state: nextRun, status: "open", error: null, refresh: vi.fn().mockResolvedValue(undefined) });
    view.rerender(<AuthoritativeRunDashboard runId="run-2" initialState={nextRun} />);

    const readiness = latestPipelineProps?.stageContent.find((content) => content.milestone.key === "readiness");
    expect(readiness?.tabs.find((tab) => tab.id === "evidence")).toBeUndefined();
    const reviewPanel = readiness?.tabs.find((tab) => tab.id === "review")?.panel;
    const panelView = render(<>{reviewPanel}</>);
    expect(panelView.queryByText("global/g02/source-integrity.json")).not.toBeInTheDocument();
    panelView.unmount();
  });

  it("does not reload unchanged gate packages for an unrelated authoritative event", async () => {
    vi.mocked(getG02Review).mockResolvedValue(g02Review("sha256:g02-package", "g02-package-artifact"));
    vi.mocked(getBaselineSummary).mockResolvedValue(g03Assessment("sha256:g03-package", "g03-package-artifact"));
    const gateEvents = [
      makeEvent("RUN_CREATED", 1),
      makeEvent("G02_CREATED", 2, { payload: { snapshot_id: "snapshot-1", package_checksum: "sha256:g02-package" } }),
      makeEvent("G02_APPROVED", 3),
      makeEvent("G03_CREATED", 4, { payload: { package_checksum: "sha256:g03-package", evidence_set_checksum: "sha256:g03-evidence" } }),
    ];
    const run = makeAuthoritativeRun({ workflow_events: gateEvents });
    const view = renderDashboard(run);
    await waitFor(() => {
      expect(getG02Review).toHaveBeenCalledOnce();
      expect(getBaselineSummary).toHaveBeenCalledOnce();
    });

    const refreshedRun = makeAuthoritativeRun({
      state_version: run.state_version + 1,
      workflow_events: [
        ...gateEvents.map((event) => ({ ...event, payload: { ...event.payload } })),
        makeEvent("RUN_NOTE_UPDATED", 5),
      ],
    });
    vi.mocked(useAuthoritativeRun).mockReturnValue({ state: refreshedRun, status: "open", error: null, refresh: vi.fn().mockResolvedValue(undefined) });
    view.rerender(<AuthoritativeRunDashboard runId={refreshedRun.run_id} initialState={refreshedRun} />);

    await waitFor(() => {
      expect(getG02Review).toHaveBeenCalledOnce();
      expect(getBaselineSummary).toHaveBeenCalledOnce();
    });
  });

  it.each([
    ["G02", "readiness", "Loading source snapshot review package", "Initialize source snapshot review"],
    ["G03", "baseline", "Loading baseline qualification package", "Qualify baseline"],
  ] as const)("keeps %s package mutation unavailable while the authoritative GET is pending", async (gate, key, loadingText, unsafeAction) => {
    if (key === "readiness") {
      vi.mocked(getG02Review).mockImplementation(() => new Promise(() => undefined));
    } else {
      vi.mocked(getG02Review).mockResolvedValue(g02Review("sha256:g02-package", "g02-package-artifact"));
      vi.mocked(getBaselineSummary).mockImplementation(() => new Promise(() => undefined));
    }
    renderDashboard(gatePackageRun(key));
    await waitFor(() => expect(gate === "G02" ? getG02Review : getBaselineSummary).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: /^Pipeline/ }));
    const panelView = render(<>{reviewPanelFor(key)}</>);

    expect(panelView.getByText(loadingText)).toBeInTheDocument();
    expect(panelView.queryByRole("button", { name: unsafeAction })).not.toBeInTheDocument();
  });

  it.each([
    ["G02", "rejected", "readiness"],
    ["G02", "invalid", "readiness"],
    ["G03", "rejected", "baseline"],
    ["G03", "invalid", "baseline"],
  ] as const)("fails closed and recovers %s review after a %s package response", async (gate, failure, key) => {
    const api = gate === "G02" ? getG02Review : getBaselineSummary;
    if (gate === "G02") {
      if (failure === "rejected") vi.mocked(getG02Review).mockRejectedValueOnce(new Error("network unavailable"));
      else vi.mocked(getG02Review).mockResolvedValueOnce({ ...g02Review("sha256:g02-package", "g02-package-artifact"), run_id: "wrong-run" });
    } else {
      vi.mocked(getG02Review).mockResolvedValue(g02Review("sha256:g02-package", "g02-package-artifact"));
      if (failure === "rejected") vi.mocked(getBaselineSummary).mockRejectedValueOnce(new Error("network unavailable"));
      else vi.mocked(getBaselineSummary).mockResolvedValueOnce({ ...g03Assessment("sha256:g03-package", "g03-package-artifact"), run_id: "wrong-run" });
    }
    renderDashboard(gatePackageRun(key));
    fireEvent.click(screen.getByRole("button", { name: /^Pipeline/ }));
    await waitFor(() => expect(api).toHaveBeenCalledOnce());
    const panelView = render(<>{reviewPanelFor(key)}</>);
    const retryName = gate === "G02" ? "Retry source snapshot review" : "Retry baseline qualification";
    const unsafeAction = gate === "G02" ? "Initialize source snapshot review" : "Qualify baseline";

    expect(panelView.getByText(/could not be loaded|is unavailable/)).toBeInTheDocument();
    expect(panelView.queryByRole("button", { name: unsafeAction })).not.toBeInTheDocument();
    if (gate === "G02") vi.mocked(getG02Review).mockResolvedValueOnce(g02Review("sha256:g02-package", "g02-package-artifact"));
    else vi.mocked(getBaselineSummary).mockResolvedValueOnce(g03Assessment("sha256:g03-package", "g03-package-artifact"));
    fireEvent.click(panelView.getByRole("button", { name: retryName }));
    await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(latestPipelineProps?.stageContent.find((content) => content.milestone.key === key)?.evidenceCount).toBe(1));
    panelView.rerender(<>{reviewPanelFor(key)}</>);

    expect(panelView.getByRole("button", { name: gate === "G02" ? "Record source snapshot decision" : "Approve baseline qualification" })).toBeInTheDocument();
    expect(panelView.queryByRole("button", { name: unsafeAction })).not.toBeInTheDocument();
  });

  it.each([
    ["unknown status", { status: "unexpected", decision: null }],
    ["inconsistent status and decision", { status: "pending", decision: "approved" }],
  ])("fails closed and GET-retries a same-run/checksum G02 response with %s", async (_case, invalidState) => {
    const validReview = g02Review("sha256:g02-package", "g02-package-artifact");
    vi.mocked(getG02Review)
      .mockResolvedValueOnce({ ...validReview, ...invalidState } as unknown as G02ReviewResponse)
      .mockResolvedValueOnce(validReview);
    renderDashboard(gatePackageRun("readiness"));
    fireEvent.click(screen.getByRole("button", { name: /^Pipeline/ }));
    await waitFor(() => expect(getG02Review).toHaveBeenCalledOnce());
    const panelView = render(<>{reviewPanelFor("readiness")}</>);

    expect(panelView.getByText("The source snapshot review package is unavailable because the response was invalid.")).toBeInTheDocument();
    expect(panelView.queryByRole("button", { name: "Record source snapshot decision" })).not.toBeInTheDocument();
    expect(panelView.queryByRole("button", { name: "Initialize source snapshot review" })).not.toBeInTheDocument();
    fireEvent.click(panelView.getByRole("button", { name: "Retry source snapshot review" }));
    await waitFor(() => expect(getG02Review).toHaveBeenCalledTimes(2));
    panelView.rerender(<>{reviewPanelFor("readiness")}</>);

    expect(panelView.getByRole("button", { name: "Record source snapshot decision" })).toBeInTheDocument();
  });

  it("renders one route heading, a skip link, human evidence, and closed technical details", () => {
    const run = makeAuthoritativeRun({
      artifacts: [makeArtifact({ relative_path: "00_job_setup/create_run_request.json" })],
    });

    renderDashboard(run);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveAccessibleName("source to source-angular-21");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#control-tower-content");
    expect(screen.getByText("Create run request")).toBeInTheDocument();
    expect(screen.getByText(run.run_id)).not.toBeVisible();
    expect(screen.getByText("Technical details").closest("details")).not.toHaveAttribute("open");
  });

  it("keeps confirmed context visible and disables fresh-state navigation during recovery", () => {
    renderDashboard(makeAuthoritativeRun(), "recovering");

    expect(screen.getByRole("heading", { name: "Authoritative state is refreshing" })).toBeInTheDocument();
    expect(screen.getByText(/Setup, Readiness, Production readiness/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Waiting for authoritative refresh" })).toBeDisabled();
  });

  it("withholds same-run transformation navigation after a background refresh failure until recovery", () => {
    const run = makeAuthoritativeRun({ run_phase: "STAGED_MIGRATION" });
    const projection = blockedTransformation(run.run_id);
    vi.mocked(useTransformation).mockReturnValue(transformationHook({
      projection,
      status: "ready",
      executionStatus: "ready",
      refreshError: "Background refresh failed; showing the last authoritative state.",
    }));
    const view = renderDashboard(run);

    expect(screen.getByRole("heading", { name: "Authoritative state is refreshing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Waiting for authoritative refresh" })).toBeDisabled();

    vi.mocked(useTransformation).mockReturnValue(transformationHook({
      projection,
      status: "ready",
      executionStatus: "ready",
      refreshError: null,
    }));
    view.rerender(<AuthoritativeRunDashboard runId={run.run_id} initialState={run} />);

    expect(screen.getByRole("heading", { name: "Transformation blocked" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View in pipeline" })).toBeEnabled();
  });

  it("presents reconnecting quietly without hiding the confirmed Overview", () => {
    renderDashboard(makeAuthoritativeRun(), "reconnecting");

    expect(screen.getByText("Connection lost · reconnecting…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("fails closed for incompatible run identifiers", () => {
    vi.mocked(useTransformation).mockReturnValue(transformationHook({
      status: "ready",
      executionStatus: "ready",
      projection: {
        run_id: "another-run",
        status: "running",
      } as TransformationProjection,
    }));

    renderDashboard();

    expect(screen.getByRole("heading", { name: "Authoritative state is refreshing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Waiting for authoritative refresh" })).toBeDisabled();
  });

  it("keeps Assistant subordinate after the primary navigation", () => {
    renderDashboard();

    expect(document.querySelector(".controlTowerAssistantSlot")).toContainElement(
      screen.getByRole("button", { name: "Open Assistant" }),
    );
    expect(screen.getAllByRole("button", { name: "Open Assistant" })).toHaveLength(1);
  });
});
