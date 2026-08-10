"use client";

import { useCallback, useMemo, useState } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import {
  TRANSFORMATION_EVENT_TYPES,
  useAuthoritativeRun,
  type AuthoritativeConnectionStatus,
} from "@/hooks/useAuthoritativeRun";
import { useTransformation } from "@/hooks/useTransformation";
import { buildRunWorkspaceProjection } from "@/presentation/currentAction";
import type { JourneyKey } from "@/presentation/runJourney";
import { presentArtifact } from "@/presentation/artifacts";
import { retryAuthoritativeSourceIntake } from "@/api/runs";
import { getBackendBaseUrl } from "@/api/client";
import { SourceSnapshotPanel } from "./SourceSnapshotPanel";
import { G02ReviewPanel } from "./G02ReviewPanel";
import { BaselineQualificationPanel } from "./BaselineQualificationPanel";
import { BaselineParityPanel } from "./BaselineParityPanel";
import { AnalysisReviewPanel } from "./AnalysisReviewPanel";
import { FeasibilityPanel } from "./FeasibilityPanel";
import { MigrationPlanPanel } from "./MigrationPlanPanel";
import { PlanReviewPanel } from "./PlanReviewPanel";
import { AuthoritativeRunCancellationPanel } from "./AuthoritativeRunCancellationPanel";
import { AssistantDock } from "./AssistantPanel";
import { LlmDiagnosticsPanel } from "./LlmDiagnosticsPanel";
import { ControlTowerHeader } from "./control-tower/ControlTowerHeader";
import { ControlTowerSidebar, type ControlTowerSection } from "./control-tower/ControlTowerSidebar";
import { OperatorOverview } from "./control-tower/OperatorOverview";
import { PipelineSection } from "./control-tower/PipelineSection";
import type { PipelineStageContent } from "./control-tower/PipelineStageDetail";
import { TechnicalDetails } from "./control-tower/TechnicalDetails";
import { WorkflowEventsSection } from "./control-tower/WorkflowEventsSection";
import styles from "./ControlTowerShell.module.css";
import "./control-tower/ControlTowerLayout.module.css";

const TRANSFORMATION_EVENT_TYPE_SET: ReadonlySet<string> = new Set(TRANSFORMATION_EVENT_TYPES);

const CONNECTION_LABELS: Record<AuthoritativeConnectionStatus, string> = {
  loading: "Loading authoritative state…",
  connecting: "Connecting to backend events…",
  open: "Live · authoritative state",
  reconnecting: "Connection lost · reconnecting…",
  recovering: "Refreshing authoritative snapshot…",
  failed: "Unable to refresh authoritative state",
};

function hasEvent(state: AuthoritativeRunStateDto, ...types: string[]) {
  return state.workflow_events.some((event) => types.includes(event.event_type));
}

const PIPELINE_GROUP_BY_KEY: Record<JourneyKey, PipelineStageContent["group"]> = {
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
};

const PIPELINE_SUMMARIES: Record<JourneyKey, string> = {
  setup: "Prepare the source boundary for authoritative migration work.",
  readiness: "Confirm the immutable source snapshot and G02 source-snapshot decision.",
  g01: "Production readiness was reviewed before this run was created.",
  baseline: "Establish and accept the known pre-migration baseline through G03.",
  discovery: "Review discovery, parity anchors, and the G04 analysis decision.",
  feasibility: "Resolve compatibility and decide whether the route may proceed through G05.",
  plan: "Review the checksum-bound migration plan and G06 execution contract.",
  "18-to-19": "Angular 18 to 19 transformation details are available when the backend exposes them.",
  "19-to-20": "Angular 19 to 20 transformation details are available when the backend exposes them.",
  "20-to-21": "Angular 20 to 21 transformation details are available when the backend exposes them.",
  validate: "Validation details are available when authoritative validation evidence exists.",
  complete: "Completion is confirmed only by the staged-migration and final-target evidence.",
};

const GATE_EVENT_BY_KEY: Partial<Record<JourneyKey, string>> = {
  readiness: "G02_CREATED",
  baseline: "G03_CREATED",
  discovery: "G04_CREATED",
  feasibility: "G05_CREATED",
  plan: "G06_CREATED",
};

const BASELINE_COMMAND_EVENTS = new Set([
  "COMMAND_QUEUED",
  "COMMAND_STARTED",
  "COMMAND_SUCCEEDED",
  "COMMAND_FAILED",
  "COMMAND_OUTPUT_AVAILABLE",
  "COMMAND_OUTPUT_CHUNK",
  "COMMAND_CANCELLED",
  "COMMAND_INTERRUPTED",
]);

function eventArtifactIds(payload: Record<string, unknown>): string[] {
  const values = [payload.artifact_id, payload.stdout_artifact_id, payload.stderr_artifact_id];
  if (Array.isArray(payload.artifact_ids)) values.push(...payload.artifact_ids);
  return values.filter((value): value is string => typeof value === "string" && value.length > 0);
}

function commandText(payload: Record<string, unknown>): string | null {
  if (typeof payload.chunk === "string" && payload.chunk.length > 0) return payload.chunk;
  if (typeof payload.command === "string" && payload.command.length > 0) return payload.command;
  if (typeof payload.executable !== "string" || payload.executable.length === 0) return null;
  const args = Array.isArray(payload.arguments)
    ? payload.arguments.filter((value): value is string => typeof value === "string")
    : [];
  return [payload.executable, ...args].join(" ");
}

export function AuthoritativeRunDashboard({
  runId,
  initialState,
}: {
  runId: string;
  initialState: AuthoritativeRunStateDto;
}) {
  const { state, status, error, refresh } = useAuthoritativeRun(runId, initialState);
  const transformationRefreshKey = useMemo(
    () => state.workflow_events.reduce(
      (latest, event) => TRANSFORMATION_EVENT_TYPE_SET.has(event.event_type) && event.sequence > latest
        ? event.sequence
        : latest,
      0,
    ),
    [state.workflow_events],
  );
  const transformationEnabled = state.run_phase === "STAGED_MIGRATION" || transformationRefreshKey > 0;
  const transformation = useTransformation(runId, {
    enabled: transformationEnabled,
    refreshKey: transformationRefreshKey,
  });
  const workspace = useMemo(
    () => buildRunWorkspaceProjection(
      state,
      transformation.projection,
      transformation.status,
      status,
      transformation.refreshError ? "refreshing" : "current",
    ),
    [state, status, transformation.projection, transformation.refreshError, transformation.status],
  );
  const artifactPresentations = useMemo(() => state.artifacts.map(presentArtifact), [state.artifacts]);

  const [activeSection, setActiveSection] = useState<ControlTowerSection>("overview");
  const [focusStage, setFocusStage] = useState<JourneyKey | undefined>();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [retryingSourceIntake, setRetryingSourceIntake] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const navigate = useCallback((section: ControlTowerSection, stageKey?: JourneyKey) => {
    if (stageKey) setFocusStage(stageKey);
    setActiveSection(section);
  }, []);

  const retrySourceIntake = useCallback(async () => {
    setRetryingSourceIntake(true);
    setRetryError(null);
    try {
      await retryAuthoritativeSourceIntake(runId, {
        expected_state_version: state.state_version,
        idempotency_key: `retry-source-intake-${runId}-${state.state_version}`,
        actor: "control-tower",
      });
      await refresh();
    } catch {
      setRetryError("The source-intake retry could not be started. Refresh the authoritative state and inspect the failure evidence.");
    } finally {
      setRetryingSourceIntake(false);
    }
  }, [refresh, runId, state.state_version]);

  const pipelineActionRequired = workspace.currentAction.section === "pipeline"
    && (workspace.currentAction.kind === "gate" || workspace.currentAction.kind === "blocked");
  const pipelineStageContent = useMemo(() => {
    const eventsById = new Map(state.workflow_events.map((event) => [event.event_id, event]));
    const artifactsById = new Map(state.artifacts.map((artifact) => [artifact.artifact_id, artifact]));

    return workspace.journey.map((milestone): PipelineStageContent => {
      const evidenceIds = new Set<string>();
      const evidenceEvent = milestone.evidenceEvent ? eventsById.get(milestone.evidenceEvent) : undefined;
      if (evidenceEvent) eventArtifactIds(evidenceEvent.payload).forEach((id) => evidenceIds.add(id));
      if (milestone.stageId) {
        state.artifacts.filter((artifact) => artifact.stage_id === milestone.stageId).forEach((artifact) => evidenceIds.add(artifact.artifact_id));
      }
      const evidence = [...evidenceIds].map((id) => artifactsById.get(id)).filter((artifact) => artifact != null);

      const gateEventType = GATE_EVENT_BY_KEY[milestone.key];
      const gateEvent = gateEventType
        ? [...state.workflow_events].reverse().find((event) => event.event_type === gateEventType)
        : undefined;
      const hasGatePackage = Boolean(gateEvent && typeof gateEvent.payload.package_checksum === "string" && gateEvent.payload.package_checksum.length > 0);

      const commandEvents = state.workflow_events.filter((event) => (
        milestone.stageId
          ? event.stage_id === milestone.stageId
          : milestone.key === "baseline" && BASELINE_COMMAND_EVENTS.has(event.event_type)
      ));
      const output = commandEvents.map((event) => commandText(event.payload)).filter((value): value is string => value != null);

      const summaryPanel = (
        <div className="pipelineHumanSummary">
          <p>{milestone.state === "unavailable" ? "Not available from the authoritative state" : PIPELINE_SUMMARIES[milestone.key]}</p>
          {milestone.key === "setup" && hasEvent(state, "SOURCE_INTAKE_FAILED") ? (
            <>
              {retryError ? <p role="alert">{retryError}</p> : null}
              <button type="button" onClick={() => void retrySourceIntake()} disabled={retryingSourceIntake}>
                {retryingSourceIntake ? "Retrying…" : "Retry source intake"}
              </button>
            </>
          ) : null}
          {milestone.key === "readiness" && !hasGatePackage ? <SourceSnapshotPanel runId={runId} initialState={state} /> : null}
          {milestone.key === "baseline" && !hasGatePackage ? (
            <BaselineQualificationPanel
              runId={runId}
              stateVersion={state.state_version}
              workflowEvents={state.workflow_events}
              refreshAuthoritativeState={refresh}
            />
          ) : null}
          {milestone.key === "discovery" && !hasGatePackage ? (
            <>
              <BaselineParityPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} workflowEvents={state.workflow_events} />
              <AnalysisReviewPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />
            </>
          ) : null}
          {milestone.key === "feasibility" && !hasGatePackage ? (
            <FeasibilityPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />
          ) : null}
          {milestone.key === "plan" && !hasGatePackage ? (
            <MigrationPlanPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />
          ) : null}
        </div>
      );
      const tabs: PipelineStageContent["tabs"] = [{ id: "summary", label: "Summary", panel: summaryPanel }];

      if (output.length > 0) {
        tabs.push({ id: "command", label: "Command output", panel: <pre className={styles.logViewer}>{output.join("\n")}</pre> });
      }
      if (evidence.length > 0) {
        tabs.push({
          id: "evidence",
          label: "Evidence",
          panel: (
            <ul className={styles.list}>
              {evidence.map((artifact) => (
                <li key={artifact.artifact_id}>
                  <a href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`} target="_blank" rel="noreferrer">
                    {presentArtifact(artifact).title}
                  </a>
                  <code>{artifact.checksum}</code>
                </li>
              ))}
            </ul>
          ),
        });
      }
      if (hasGatePackage) {
        let panel: React.ReactNode = null;
        if (milestone.key === "readiness") panel = <><SourceSnapshotPanel runId={runId} initialState={state} /><G02ReviewPanel runId={runId} initialState={state} /></>;
        else if (milestone.key === "baseline") panel = <BaselineQualificationPanel runId={runId} stateVersion={state.state_version} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />;
        else if (milestone.key === "discovery") panel = <><BaselineParityPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} workflowEvents={state.workflow_events} /><AnalysisReviewPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} /></>;
        else if (milestone.key === "feasibility") panel = <FeasibilityPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} />;
        else if (milestone.key === "plan") panel = <><MigrationPlanPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} /><PlanReviewPanel runId={runId} initialState={state} connectionStatus={status} refreshAuthoritativeState={refresh} /></>;
        if (panel) tabs.push({ id: "review", label: "Review", panel });
      }

      return {
        milestone,
        group: PIPELINE_GROUP_BY_KEY[milestone.key],
        occurredAt: evidenceEvent?.occurred_at ?? gateEvent?.occurred_at ?? null,
        evidenceCount: evidence.length > 0 ? evidence.length : null,
        tabs,
      };
    });
  }, [refresh, retryError, retrySourceIntake, retryingSourceIntake, runId, state, status, workspace.journey]);

  return (
    <div className="controlTowerDashboard">
      <a className="controlTowerSkipLink" href="#control-tower-content">Skip to main content</a>
      <ControlTowerSidebar
        activeSection={activeSection}
        open={navigationOpen}
        actionRequired={pipelineActionRequired}
        onSelect={setActiveSection}
        onClose={() => setNavigationOpen(false)}
        assistant={(
          <AssistantDock
            runId={state.run_id}
            phase={state.run_phase}
            stateVersion={state.state_version}
            workflowStatus={state.status}
          />
        )}
      />
      <main className="controlTowerMain" id="control-tower-content" tabIndex={-1}>
        <ControlTowerHeader
          runId={state.run_id}
          status={status}
          connectionLabel={CONNECTION_LABELS[status]}
          onMenu={() => setNavigationOpen(true)}
          state={state}
        />
        <div className="controlTowerContent">
          {activeSection === "overview" ? (
            <OperatorOverview
              projection={workspace}
              run={state}
              transformation={transformation.projection}
              transformationStatus={transformation.status}
              artifacts={artifactPresentations}
              onNavigate={navigate}
              error={error ?? transformation.refreshError}
            />
          ) : null}

          {activeSection === "pipeline" ? (
            <section className="controlTowerSection" aria-labelledby="pipeline-navigation-item">
              <div className="controlTowerSectionIntro">
                <div><h2>Pipeline</h2><p>Authoritative work across the migration journey.</p></div>
              </div>
              <PipelineSection
                journey={workspace.journey}
                stageContent={pipelineStageContent}
                focusStage={focusStage}
              />
            </section>
          ) : null}

          {activeSection === "evidence" ? (
            <section className="controlTowerSection" aria-labelledby="evidence-navigation-item">
              <div className="controlTowerSectionIntro">
                <div><h2>Evidence</h2><p>Immutable artifacts registered by the backend.</p></div>
              </div>
              <section className={styles.panel} aria-label="Run evidence">
                {artifactPresentations.length === 0 ? <p className={styles.note}>Evidence not available.</p> : (
                  <ul className={styles.list}>
                    {artifactPresentations.map((presentation) => (
                      <li key={presentation.artifact.artifact_id}>
                        <a
                          className={styles.actionLink}
                          href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(presentation.artifact.artifact_id)}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {presentation.title}
                        </a>
                        <span>{presentation.stageLabel}</span>
                        <code>{presentation.rawPath}</code>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </section>
          ) : null}

          {activeSection === "diagnostics" ? (
            <section className="controlTowerSection" aria-labelledby="diagnostics-navigation-item">
              <div className="controlTowerSectionIntro">
                <div><h2>Diagnostics</h2><p>Connection, blockers, events, commands, and provider evidence.</p></div>
              </div>
              <section className={styles.panel} aria-label="Connection diagnostics">
                <h3>Authoritative connection</h3>
                <p className={styles.note}>{CONNECTION_LABELS[status]}</p>
                {error ? <p role="alert">{error}</p> : null}
                {transformation.loadError ? <p role="alert">Transformation state could not be loaded.</p> : null}
                {transformation.refreshError ? <p role="status">{transformation.refreshError}</p> : null}
              </section>
              <WorkflowEventsSection events={state.workflow_events} />
              <LlmDiagnosticsPanel
                runId={runId}
                stateVersion={state.state_version}
                connectionStatus={status}
                refreshAuthoritativeState={refresh}
                workflowEvents={state.workflow_events}
              />
              <TechnicalDetails title="Run controls">
                <AuthoritativeRunCancellationPanel runId={runId} state={state} refresh={refresh} />
              </TechnicalDetails>
            </section>
          ) : null}
        </div>
      </main>
    </div>
  );
}
