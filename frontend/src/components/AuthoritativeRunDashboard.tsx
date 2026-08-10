"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AuthoritativeRunStateDto, BaselineAssessmentResponse, G02ReviewResponse, WorkflowEventDto } from "@/types/generated/api";
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
import { getG02Review } from "@/api/g02";
import { getBaselineSummary } from "@/api/baselineG03";
import { getBackendBaseUrl } from "@/api/client";
import { SourceSnapshotPanel } from "./SourceSnapshotPanel";
import { G02ReviewPanel, validG02StatusDecision } from "./G02ReviewPanel";
import { BaselineQualificationPanel } from "./BaselineQualificationPanel";
import { BaselineParityPanel } from "./BaselineParityPanel";
import { AnalysisReviewPanel } from "./AnalysisReviewPanel";
import { FeasibilityPanel } from "./FeasibilityPanel";
import { MigrationPlanPanel } from "./MigrationPlanPanel";
import { PlanReviewPanel } from "./PlanReviewPanel";
import { TransformationPanel } from "./TransformationPanel";
import { AuthoritativeRunCancellationPanel } from "./AuthoritativeRunCancellationPanel";
import { AssistantDock } from "./AssistantPanel";
import { LlmDiagnosticsPanel } from "./LlmDiagnosticsPanel";
import { ControlTowerHeader } from "./control-tower/ControlTowerHeader";
import { ControlTowerSidebar, type ControlTowerSection } from "./control-tower/ControlTowerSidebar";
import { OperatorOverview } from "./control-tower/OperatorOverview";
import { PipelineSection } from "./control-tower/PipelineSection";
import type { PipelineStageContent } from "./control-tower/PipelineStageDetail";
import type { AuthoritativePackageLoad } from "./control-tower/authoritativePackageLoad";
import { TechnicalDetails } from "./control-tower/TechnicalDetails";
import { WorkflowEventsSection } from "./control-tower/WorkflowEventsSection";
import { EvidenceWorkspace } from "./control-tower/EvidenceWorkspace";
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

function automaticPipelineKey(journey: ReturnType<typeof buildRunWorkspaceProjection>["journey"]): JourneyKey | undefined {
  return journey.find((milestone) => milestone.state === "action-required")?.key
    ?? journey.find((milestone) => milestone.state === "current")?.key;
}

function latestEvent(events: WorkflowEventDto[], eventType: string): WorkflowEventDto | undefined {
  return [...events].reverse().find((event) => event.event_type === eventType);
}

function latestGateEventId(events: WorkflowEventDto[], gateId: "G02" | "G03", createdSequence: number): string {
  return [...events].reverse().find((event) => event.sequence >= createdSequence && event.event_type.startsWith(`${gateId}_`))?.event_id ?? "";
}

function validG02Review(value: G02ReviewResponse, runId: string, packageChecksum: string): boolean {
  return value.run_id === runId
    && value.gate_id === "G02"
    && validG02StatusDecision(value)
    && value.package?.run_id === runId
    && value.package.gate_id === "G02"
    && value.package.package_checksum === packageChecksum
    && Array.isArray(value.package.artifacts)
    && value.package.artifacts.every((artifact) => artifact.run_id === runId && typeof artifact.artifact_id === "string" && artifact.artifact_id.length > 0);
}

function validG03Assessment(value: BaselineAssessmentResponse, runId: string, packageChecksum: string, evidenceSetChecksum: string): boolean {
  return value.run_id === runId
    && value.package_checksum === packageChecksum
    && value.evidence_set_checksum === evidenceSetChecksum
    && Array.isArray(value.artifact_ids)
    && value.artifact_ids.every((artifactId) => typeof artifactId === "string" && artifactId.length > 0);
}

type PackageLoadRecord<T> =
  | { requestKey: string; status: "loading" | "unavailable" | "error" }
  | { requestKey: string; status: "ready"; value: T };

function authoritativePackageLoad<T>(record: PackageLoadRecord<T>, requestKey: string, retry: () => void): AuthoritativePackageLoad<T> {
  if (record.requestKey !== requestKey) return { status: "loading" };
  if (record.status === "ready") return { status: "ready", value: record.value };
  if (record.status === "loading") return { status: "loading" };
  return { status: record.status, retry };
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
  const authoritativePipelineKey = automaticPipelineKey(workspace.journey);
  const [expandedStage, setExpandedStage] = useState<JourneyKey | undefined>(authoritativePipelineKey ?? workspace.journey[0]?.key);
  const previousAuthoritativePipelineKey = useRef(authoritativePipelineKey);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [retryingSourceIntake, setRetryingSourceIntake] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [g02LoadRecord, setG02LoadRecord] = useState<PackageLoadRecord<G02ReviewResponse>>({ requestKey: "", status: "loading" });
  const [g03LoadRecord, setG03LoadRecord] = useState<PackageLoadRecord<BaselineAssessmentResponse>>({ requestKey: "", status: "loading" });
  const [g02RetryVersion, setG02RetryVersion] = useState(0);
  const [g03RetryVersion, setG03RetryVersion] = useState(0);

  useEffect(() => {
    if (authoritativePipelineKey && authoritativePipelineKey !== previousAuthoritativePipelineKey.current) {
      setExpandedStage(authoritativePipelineKey);
    }
    previousAuthoritativePipelineKey.current = authoritativePipelineKey;
  }, [authoritativePipelineKey]);

  const g02Created = useMemo(() => latestEvent(state.workflow_events, "G02_CREATED"), [state.workflow_events]);
  const g03Created = useMemo(() => latestEvent(state.workflow_events, "G03_CREATED"), [state.workflow_events]);
  const g02CreatedEventId = g02Created?.event_id ?? "";
  const g03CreatedEventId = g03Created?.event_id ?? "";
  const g02PackageChecksum = typeof g02Created?.payload.package_checksum === "string" ? g02Created.payload.package_checksum : "";
  const g03PackageChecksum = typeof g03Created?.payload.package_checksum === "string" ? g03Created.payload.package_checksum : "";
  const g03EvidenceSetChecksum = typeof g03Created?.payload.evidence_set_checksum === "string" ? g03Created.payload.evidence_set_checksum : "";
  const g02RefreshEventId = g02Created ? latestGateEventId(state.workflow_events, "G02", g02Created.sequence) : "";
  const g03RefreshEventId = g03Created ? latestGateEventId(state.workflow_events, "G03", g03Created.sequence) : "";
  const g02RequestKey = `${runId}|${g02CreatedEventId}|${g02PackageChecksum}|${g02RefreshEventId}`;
  const g03RequestKey = `${runId}|${g03CreatedEventId}|${g03PackageChecksum}|${g03EvidenceSetChecksum}|${g03RefreshEventId}`;
  const retryG02Review = useCallback(() => {
    setG02LoadRecord({ requestKey: g02RequestKey, status: "loading" });
    setG02RetryVersion((version) => version + 1);
  }, [g02RequestKey]);
  const retryG03Assessment = useCallback(() => {
    setG03LoadRecord({ requestKey: g03RequestKey, status: "loading" });
    setG03RetryVersion((version) => version + 1);
  }, [g03RequestKey]);
  const authoritativeG02Load = useMemo(
    () => authoritativePackageLoad(g02LoadRecord, g02RequestKey, retryG02Review),
    [g02LoadRecord, g02RequestKey, retryG02Review],
  );
  const authoritativeG03Load = useMemo(
    () => authoritativePackageLoad(g03LoadRecord, g03RequestKey, retryG03Assessment),
    [g03LoadRecord, g03RequestKey, retryG03Assessment],
  );
  const authoritativeG02Review = authoritativeG02Load.status === "ready" ? authoritativeG02Load.value : null;
  const authoritativeG03Assessment = authoritativeG03Load.status === "ready" ? authoritativeG03Load.value : null;

  useEffect(() => {
    let active = true;
    if (!g02CreatedEventId || !g02PackageChecksum) {
      return () => { active = false; };
    }
    setG02LoadRecord({ requestKey: g02RequestKey, status: "loading" });
    void getG02Review(runId).then((value) => {
      if (!active) return;
      setG02LoadRecord(validG02Review(value, runId, g02PackageChecksum)
        ? { requestKey: g02RequestKey, status: "ready", value }
        : { requestKey: g02RequestKey, status: "unavailable" });
    }).catch(() => { if (active) setG02LoadRecord({ requestKey: g02RequestKey, status: "error" }); });
    return () => { active = false; };
  }, [g02CreatedEventId, g02PackageChecksum, g02RefreshEventId, g02RequestKey, g02RetryVersion, runId]);

  useEffect(() => {
    let active = true;
    if (!g03CreatedEventId || !g03PackageChecksum || !g03EvidenceSetChecksum) {
      return () => { active = false; };
    }
    setG03LoadRecord({ requestKey: g03RequestKey, status: "loading" });
    void getBaselineSummary(runId).then((value) => {
      if (!active) return;
      setG03LoadRecord(validG03Assessment(value, runId, g03PackageChecksum, g03EvidenceSetChecksum)
        ? { requestKey: g03RequestKey, status: "ready", value }
        : { requestKey: g03RequestKey, status: "unavailable" });
    }).catch(() => { if (active) setG03LoadRecord({ requestKey: g03RequestKey, status: "error" }); });
    return () => { active = false; };
  }, [g03CreatedEventId, g03EvidenceSetChecksum, g03PackageChecksum, g03RefreshEventId, g03RequestKey, g03RetryVersion, runId]);

  const navigate = useCallback((section: ControlTowerSection, stageKey?: JourneyKey) => {
    if (stageKey) {
      setFocusStage(stageKey);
      setExpandedStage(stageKey);
    }
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
      const evidenceEvents = milestone.evidenceEvents?.map((eventId) => eventsById.get(eventId)).filter((event) => event != null)
        ?? (evidenceEvent ? [evidenceEvent] : []);
      evidenceEvents.forEach((event) => eventArtifactIds(event.payload).forEach((id) => evidenceIds.add(id)));
      if (milestone.key === "readiness" && authoritativeG02Review) {
        authoritativeG02Review.package.artifacts.forEach((artifact) => evidenceIds.add(artifact.artifact_id));
      }
      if (milestone.key === "baseline" && authoritativeG03Assessment) {
        authoritativeG03Assessment.artifact_ids.forEach((artifactId) => evidenceIds.add(artifactId));
      }
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
      const isCurrentTransformation = milestone.stageId != null
        && milestone.stageId === transformation.projection?.stage_id;

      const summaryPanel = (
        isCurrentTransformation ? (
          <TransformationPanel
            runId={runId}
            projection={transformation.projection}
            projectionStatus={transformation.status}
            executions={transformation.executions}
            executionStatus={transformation.executionStatus}
            workflowEvents={state.workflow_events}
            artifacts={state.artifacts}
            refreshTransformation={transformation.refresh}
            refreshAuthoritativeState={refresh}
          />
        ) : <div className="pipelineHumanSummary">
          <p>{milestone.state === "unavailable" ? "Not available from the authoritative state" : PIPELINE_SUMMARIES[milestone.key]}</p>
          {milestone.key === "setup" && hasEvent(state, "SOURCE_INTAKE_FAILED") ? (
            <>
              {retryError ? <p role="alert">{retryError}</p> : null}
              <button type="button" onClick={() => void retrySourceIntake()} disabled={retryingSourceIntake}>
                {retryingSourceIntake ? "Retrying…" : "Retry source intake"}
              </button>
            </>
          ) : null}
          {milestone.key === "readiness" && !hasGatePackage ? <SourceSnapshotPanel runId={runId} initialState={state} headingLevel={4} /> : null}
          {milestone.key === "baseline" && !hasGatePackage ? (
            <BaselineQualificationPanel
              runId={runId}
              stateVersion={state.state_version}
              workflowEvents={state.workflow_events}
              refreshAuthoritativeState={refresh}
              headingLevel={4}
            />
          ) : null}
          {milestone.key === "discovery" && !hasGatePackage ? (
            <>
              <BaselineParityPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} workflowEvents={state.workflow_events} headingLevel={4} />
              <AnalysisReviewPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} headingLevel={4} />
            </>
          ) : null}
          {milestone.key === "feasibility" && !hasGatePackage ? (
            <FeasibilityPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} headingLevel={4} />
          ) : null}
          {milestone.key === "plan" && !hasGatePackage ? (
            <MigrationPlanPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} headingLevel={4} />
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
        if (milestone.key === "readiness") panel = <><SourceSnapshotPanel runId={runId} initialState={state} headingLevel={4} /><G02ReviewPanel runId={runId} initialState={state} authoritativeReview={authoritativeG02Load} refreshAuthoritativeState={refresh} headingLevel={4} /></>;
        else if (milestone.key === "baseline") panel = <BaselineQualificationPanel runId={runId} stateVersion={state.state_version} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} authoritativeAssessment={authoritativeG03Load} headingLevel={4} />;
        else if (milestone.key === "discovery") panel = <><BaselineParityPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} workflowEvents={state.workflow_events} headingLevel={4} /><AnalysisReviewPanel runId={runId} stateVersion={state.state_version} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} headingLevel={4} /></>;
        else if (milestone.key === "feasibility") panel = <FeasibilityPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} headingLevel={4} />;
        else if (milestone.key === "plan") panel = <><MigrationPlanPanel runId={runId} initialState={state} connectionStatus={status} artifacts={state.artifacts} workflowEvents={state.workflow_events} refreshAuthoritativeState={refresh} headingLevel={4} /><PlanReviewPanel runId={runId} initialState={state} connectionStatus={status} refreshAuthoritativeState={refresh} headingLevel={4} /></>;
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
  }, [authoritativeG02Load, authoritativeG02Review, authoritativeG03Assessment, authoritativeG03Load, refresh, retryError, retrySourceIntake, retryingSourceIntake, runId, state, status, transformation.executionStatus, transformation.executions, transformation.projection, transformation.refresh, transformation.status, workspace.journey]);

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
                expandedKey={expandedStage}
                onExpandedKeyChange={setExpandedStage}
              />
            </section>
          ) : null}

          {activeSection === "evidence" ? (
            <section className="controlTowerSection" aria-labelledby="evidence-navigation-item">
              <EvidenceWorkspace artifacts={artifactPresentations} />
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
