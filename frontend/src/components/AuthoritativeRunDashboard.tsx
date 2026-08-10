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
import { AuthoritativeRunCancellationPanel } from "./AuthoritativeRunCancellationPanel";
import { AssistantDock } from "./AssistantPanel";
import { LlmDiagnosticsPanel } from "./LlmDiagnosticsPanel";
import { ControlTowerHeader } from "./control-tower/ControlTowerHeader";
import { ControlTowerSidebar, type ControlTowerSection } from "./control-tower/ControlTowerSidebar";
import { OperatorOverview } from "./control-tower/OperatorOverview";
import { PipelineSection } from "./control-tower/PipelineSection";
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

  const qualificationAvailable = (hasEvent(state, "G02_APPROVED") && hasEvent(state, "BASELINE_INSTALL_SUCCEEDED"))
    || hasEvent(state, "BASELINE_BLOCKED", "BASELINE_QUALIFIED", "G03_CREATED", "G03_APPROVED", "G03_REJECTED");
  const qualificationActionRequired = qualificationAvailable && !hasEvent(state, "G03_APPROVED");
  const g02Available = hasEvent(state, "G02_CREATED", "G02_APPROVED", "G02_REJECTED", "G02_STALE")
    || (state.status === "SOURCE_VALIDATED" && state.approval_status === "pending" && hasEvent(state, "SNAPSHOT_CREATED"));
  const g02ActionRequired = g02Available && !hasEvent(state, "G02_APPROVED", "G02_REJECTED", "G02_STALE");
  const pipelineActionRequired = workspace.currentAction.section === "pipeline"
    && (workspace.currentAction.kind === "gate" || workspace.currentAction.kind === "blocked");
  const shared = { runId, initialState: state };

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
                state={state}
                retryError={retryError}
                retrying={retryingSourceIntake}
                onRetry={() => void retrySourceIntake()}
                qualificationAvailable={qualificationAvailable}
                qualificationActionRequired={qualificationActionRequired}
                g02ActionRequired={g02ActionRequired}
                focusStage={focusStage}
              >
                {(selectedStage) => <>
                  {selectedStage === "Source review & G02" ? <><SourceSnapshotPanel {...shared} /><G02ReviewPanel {...shared} /></> : null}
                  {selectedStage === "Baseline qualification" ? (
                    <BaselineQualificationPanel
                      runId={runId}
                      stateVersion={state.state_version}
                      workflowEvents={state.workflow_events}
                      refreshAuthoritativeState={refresh}
                    />
                  ) : null}
                </>}
              </PipelineSection>
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
