import type { ReactNode } from "react";
import type { ArtifactRefDto, CommandExecutionResponseDto, WorkflowEventDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";
import { getBackendBaseUrl } from "@/api/client";
import { TRANSFORMATION_EVENT_TYPES } from "@/hooks/useAuthoritativeRun";
import { LiveCommandLogViewer } from "@/components/LogViewer";
import { UnifiedDiffViewer } from "@/components/UnifiedDiffViewer";
import styles from "./TransformationPanel.module.css";

type SharedProps = {
  projection: TransformationProjection;
  workflowEvents: WorkflowEventDto[];
  artifacts: ArtifactRefDto[];
  executions: CommandExecutionResponseDto[];
  executionStatus: "loading" | "ready" | "unavailable";
};

const transformerEvents = new Set<string>(TRANSFORMATION_EVENT_TYPES);
const transformationEvent = (event: WorkflowEventDto) => transformerEvents.has(event.event_type);

function latest(events: WorkflowEventDto[], matches: (type: string) => boolean) {
  return events.filter((event) => matches(event.event_type)).at(-1);
}

const decisionLabels: Record<string, string> = {
  G07: "Stage-start approval",
  G08: "Validation review",
  G09: "Validation evidence review",
  G10: "Repair approval",
  G11: "Final stage acceptance",
  G12: "Delivery approval",
};

export function decisionLabel(value: string | null | undefined) {
  return value ? decisionLabels[value] ?? "Unsupported decision" : "No decision requested";
}

export function displayStatus(value: string | null | undefined) {
  if (!value) return "Unavailable";
  const known: Record<string, string> = {
    sealed: "Sealed",
    prepared: "Prepared",
    passed: "Passed",
    completed: "Completed",
    succeeded: "Succeeded",
    failed: "Failed",
    waiting_gate: "Waiting for approval",
    waiting_command: "Command in progress",
    running: "Running",
    queued: "Queued",
    pending: "Pending",
    blocked: "Blocked",
    cancelled: "Cancelled",
    rejected: "Rejected",
  };
  return known[value.toLowerCase()] ?? "Unavailable";
}

function evidenceLabel(value: string) {
  const decision = Object.keys(decisionLabels).find((key) => value.startsWith(`${key}_`));
  if (decision) return decisionLabel(decision);
  return value.replaceAll("_", " ").toLowerCase();
}

export function TechnicalDetails({ children }: { children: ReactNode }) {
  return <details className={styles.technical}><summary>Technical details</summary><div className={styles.technicalBody}>{children}</div></details>;
}

function attemptIdFromPath(path: string): string | null {
  const match = /attempt-([^/]+)\//.exec(path);
  return match ? match[1] : null;
}

function EvidenceLinks({
  artifacts,
  matches,
  empty,
  activeAttemptId = null,
}: {
  artifacts: ArtifactRefDto[];
  matches: (path: string) => boolean;
  empty: string;
  activeAttemptId?: string | null;
}) {
  const visible = artifacts.filter((artifact) => matches(artifact.relative_path));
  if (visible.length === 0) return <p className={styles.note}>{empty}</p>;
  return <ul className={styles.artifactList}>
    {visible.map((artifact) => {
      const attemptId = attemptIdFromPath(artifact.relative_path);
      const historical = activeAttemptId !== null && attemptId !== null && attemptId !== activeAttemptId;
      return <li key={artifact.artifact_id}>
        <a
          href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`}
          target="_blank"
          rel="noreferrer"
        >
          {artifact.relative_path}
        </a>
        {historical ? <small className={styles.historical}>Historical attempt evidence</small> : null}
        <TechnicalDetails>
          <code>Artifact ID: {artifact.artifact_id}</code>
          <code>Checksum: {artifact.checksum}</code>
        </TechnicalDetails>
      </li>;
    })}
  </ul>;
}

export function StageSummary({ projection }: Omit<SharedProps, "artifacts">) {
  const currentStageIndex = projection.route_stages.findIndex((stage) => stage.stage_id === projection.stage_id);
  const previousStage = currentStageIndex > 0 ? projection.route_stages[currentStageIndex - 1] : null;
  return <section className={styles.card} aria-labelledby="transform-stage-summary">
    <span className={styles.eyebrow}>01 / Stage and continuation</span>
    <h3 id="transform-stage-summary">Migration stages</h3>
    <dl className={styles.metadata}>
      <div><dt>Angular route</dt><dd>{projection.source_version ?? "unavailable"} → {projection.target_version ?? "unavailable"}</dd></div>
      <div><dt>Active stage</dt><dd>{displayStatus(projection.stage_status)}</dd></div>
      <div><dt>Continuation</dt><dd>{displayStatus(projection.status)}</dd></div>
      <div><dt>Workspace lineage</dt><dd>{projection.stage_start_fingerprint ? "Bound and fingerprinted" : "Unavailable"}</dd></div>
      <div><dt>Previous sealed input</dt><dd>{previousStage?.status.toLowerCase() === "sealed"
        ? `Angular ${previousStage.source_version ?? "unavailable"} to ${previousStage.target_version ?? "unavailable"} sealed output`
        : currentStageIndex > 0 ? "Unavailable" : "Not applicable"}</dd></div>
    </dl>
    <ol className={styles.route} aria-label="Migration stage route">
      {projection.route_stages.length === 0
        ? <li><span>Stage route unavailable</span></li>
        : projection.route_stages.map((stage) => <li key={stage.stage_id}>
            <strong>Angular {stage.source_version ?? "unavailable"} to {stage.target_version ?? "unavailable"}</strong>
            <span>{displayStatus(stage.status)}{stage.stage_id === projection.stage_id ? " · Active stage" : ""}</span>
          </li>)}
    </ol>
    <TechnicalDetails>
      <code>Stage ID: {projection.stage_id}</code>
      <code>Continuation ID: {projection.continuation_id}</code>
      <code>Workflow node: {projection.current_node}</code>
      <code>Workflow step: {projection.workflow_step}</code>
      <code>State version: {projection.state_version}</code>
      <code>Checkpoint: {projection.checkpoint_kind ?? "unavailable"}</code>
      <code>Workspace fingerprint: {projection.workspace_fingerprint ?? "unavailable"}</code>
      <code>Stage-start fingerprint: {projection.stage_start_fingerprint ?? "unavailable"}</code>
      <code>Sealed manifest checksum: {projection.stage_status.toLowerCase() === "sealed" ? projection.sealed_chain_hash ?? "unavailable" : "not sealed for active stage"}</code>
    </TechnicalDetails>
  </section>;
}

export function WorkerStatus({ projection }: { projection: TransformationProjection }) {
  return <section className={styles.card} aria-labelledby="transform-worker-status">
    <span className={styles.eyebrow}>02 / Worker and command</span>
    <h3 id="transform-worker-status">Durable execution</h3>
    <dl className={styles.metadata}>
      <div><dt>Worker state</dt><dd>{displayStatus(projection.status)}</dd></div>
      <div><dt>Active command</dt><dd>{projection.active_command_id ? displayStatus(projection.active_command_status) : "No command in progress"}</dd></div>
      <div><dt>Cancellation</dt><dd>{projection.cancel_requested_at ? "Requested" : "Not requested"}</dd></div>
    </dl>
    <TechnicalDetails>
      <code>Continuation ID: {projection.continuation_id}</code>
      <code>Command ID: {projection.active_command_id ?? "unavailable"}</code>
      <code>Command phase: {projection.active_command_phase ?? "unavailable"}</code>
      <code>Checkpoint: {projection.checkpoint_kind ?? "unavailable"}</code>
      <code>Cancellation timestamp: {projection.cancel_requested_at ?? "unavailable"}</code>
    </TechnicalDetails>
  </section>;
}

function timestamp(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "Unavailable";
}

function retryParent(executionId: string, workflowEvents: WorkflowEventDto[]) {
  const event = workflowEvents
    .filter((item) => ["COMMAND_QUEUED", "COMMAND_STARTED"].includes(item.event_type))
    .reverse()
    .find((item) => item.payload.execution_id === executionId);
  return typeof event?.payload.parent_execution_id === "string" ? event.payload.parent_execution_id : null;
}

function ExecutionHistory({ projection, workflowEvents, executions, executionStatus }: Pick<SharedProps, "projection" | "workflowEvents" | "executions" | "executionStatus">) {
  return <section className={styles.repairSection} aria-labelledby="transform-execution-history">
    <h4 id="transform-execution-history">Execution history</h4>
    {executionStatus === "loading" ? <p role="status">Loading execution history...</p> : null}
    {executionStatus === "unavailable" ? <p className={styles.alert} role="alert">Execution history is unavailable from the backend. No execution result is inferred.</p> : null}
    {executionStatus === "ready" && executions.length === 0 ? <p className={styles.note}>No command executions are projected.</p> : null}
    {executions.length > 0 ? <ul className={styles.artifactList}>
      {executions.map((execution) => {
        const currentStage = execution.stage_id === projection.stage_id;
        const routeStage = projection.route_stages.find((stage) => stage.stage_id === execution.stage_id);
        const parent = retryParent(execution.execution_id, workflowEvents);
        const failure = execution.failure_reason ?? execution.failure_code;
        return <li key={execution.execution_id}>
          <strong>{execution.command_id}</strong>
          <span>{displayStatus(execution.status)} · {currentStage ? "Current stage" : "Historical stage"}</span>
          {routeStage ? <span>Angular {routeStage.source_version ?? "unavailable"} to {routeStage.target_version ?? "unavailable"}</span> : null}
          {failure ? <span className={styles.alert}>Failure: {failure}</span> : null}
          <TechnicalDetails>
            <code>Execution ID: {execution.execution_id}</code>
            <code>Stage ID: {execution.stage_id ?? "unavailable"}</code>
            <code>Exit code: {execution.exit_code ?? "unavailable"}</code>
            <code>Started: {timestamp(execution.started_at)}</code>
            <code>Completed: {timestamp(execution.completed_at)}</code>
            <code>Retry parent: {parent ?? "Not projected"}</code>
            <code>Artifacts: {execution.artifact_ids.length ? execution.artifact_ids.join(", ") : "none"}</code>
            <code>Workspace fingerprint: {currentStage ? projection.workspace_fingerprint ?? "unavailable" : "Not projected for historical execution"}</code>
          </TechnicalDetails>
        </li>;
      })}
    </ul> : null}
  </section>;
}

export function LogsAndDiagnostics({ projection, workflowEvents, executions, executionStatus }: Omit<SharedProps, "artifacts">) {
  const currentDiagnostic = latest(workflowEvents.filter((event) => event.stage_id === projection.stage_id && transformationEvent(event)), () => true);
  const historicalEvent = latest(workflowEvents.filter((event) => event.stage_id !== projection.stage_id && transformationEvent(event)), () => true);
  const diagnostic = currentDiagnostic ?? historicalEvent;
  const isHistoricalDiagnostic = Boolean(
    diagnostic
    && !currentDiagnostic,
  );
  return <section className={`${styles.card} ${styles.cardWide}`} aria-labelledby="transform-logs">
    <span className={styles.eyebrow}>04 / Logs and diagnostics</span>
    <h3 id="transform-logs">Command output</h3>
    {projection.active_command_id
      ? <LiveCommandLogViewer
          runId={projection.run_id}
          executionId={projection.active_command_id}
          executionStatus={projection.active_command_status ?? undefined}
        />
      : <p className={styles.note}>No Transformer command is currently projected.</p>}
    {diagnostic ? <>
      <p className={styles.event}>
        Latest workflow evidence{isHistoricalDiagnostic ? " (historical/resolved)" : ""}: {evidenceLabel(diagnostic.event_type)}
      </p>
      {Object.keys(diagnostic.payload).length > 0
        ? <pre className={styles.diagnostics}>{JSON.stringify(diagnostic.payload, null, 2)}</pre>
        : null}
    </> : null}
    {(projection.active_error ?? (projection.last_error_code
      ? { code: projection.last_error_code, message: projection.last_error_message }
      : null)) ? <div className={styles.alert} role="alert">
      <p>Current blocker</p>
      {(projection.active_error?.message ?? projection.last_error_message) ? <p>{projection.active_error?.message ?? projection.last_error_message}</p> : <p>The backend reported a blocker without a message.</p>}
      <TechnicalDetails><code>Blocker code: {projection.active_error?.code ?? projection.last_error_code}</code></TechnicalDetails>
      {projection.runtime_profile_binding
        ? <pre className={styles.diagnostics}>{JSON.stringify(projection.runtime_profile_binding, null, 2)}</pre>
        : null}
    </div> : null}
    {projection.historical_diagnostics.map((item) => <div key={`${item.code}-${item.message}`} className={styles.note}>
      <strong>Historical/resolved failure</strong>
      {item.message ? <p>{item.message}</p> : null}
      <TechnicalDetails><code>Diagnostic code: {item.code}</code></TechnicalDetails>
    </div>)}
    <ExecutionHistory projection={projection} workflowEvents={workflowEvents} executions={executions} executionStatus={executionStatus} />
  </section>;
}

export function TransformationEvidence({ projection, workflowEvents, artifacts }: SharedProps) {
  const version = latest(workflowEvents, (type) => type.startsWith("VERSION_VERIFICATION_"));
  const completed = latest(workflowEvents, (type) => type === "STAGE_TRANSFORMATION_COMPLETED");
  const versionStatus = version?.event_type === "VERSION_VERIFICATION_PASSED" ? "Passed" : version ? "Failed or unavailable" : "Unavailable";
  return <section className={styles.card} aria-labelledby="transform-evidence">
    <span className={styles.eyebrow}>06 / Version and transformation evidence</span>
    <h3 id="transform-evidence">Dependency and version evidence</h3>
    <dl className={styles.metadata}>
      <div><dt>Version verification</dt><dd>{versionStatus}</dd></div>
      <div><dt>Angular update</dt><dd>{completed ? "Completed" : "Unavailable"}</dd></div>
      <div><dt>Dependency closure</dt><dd>{projection.dependency_closure ? "Recorded" : "Unavailable"}</dd></div>
    </dl>
    <p className={styles.note}>The backend projection does not expose a separate installed-version result object; the version event and transformation artifacts are shown as evidence, not inferred as a new state.</p>
    <EvidenceLinks
      artifacts={artifacts}
      matches={(path) => path.includes(`/stages/${projection.stage_id}/transformation/`)}
      empty="Version proof and migration-ledger artifacts are not available yet."
    />
  </section>;
}

export function ValidationEvidence({ projection, workflowEvents, artifacts }: SharedProps) {
  const validation = latest(workflowEvents, (type) => type.startsWith("STAGE_VALIDATION_"));
  return <section className={styles.card} aria-labelledby="transform-validation">
    <span className={styles.eyebrow}>07 / Build and test validation</span>
    <h3 id="transform-validation">Frozen validation</h3>
    <dl className={styles.metadata}>
      <div><dt>Install</dt><dd>{displayStatus(projection.validation_results.npm_ci?.status)}</dd></div>
      <div><dt>Production build</dt><dd>{displayStatus(projection.validation_results.build?.status)}</dd></div>
      <div><dt>Tests</dt><dd>{displayStatus(projection.validation_results.test?.status)}</dd></div>
      <div><dt>Validation review</dt><dd>{validation?.event_type === "STAGE_VALIDATION_COMPLETED" ? "Recorded" : validation ? "Failed or unavailable" : "Unavailable"}</dd></div>
      <div><dt>Final stage acceptance</dt><dd>{projection.stage_status.toLowerCase() === "sealed" ? "Recorded with sealed stage" : "Unavailable"}</dd></div>
    </dl>
    <p className={styles.note}>Build, test, and install status come from the backend validation projection. Missing values remain unavailable.</p>
    <EvidenceLinks
      artifacts={artifacts}
      matches={(path) =>
        path.includes(`/stages/${projection.stage_id}/validation/`)
        || path.includes(`/stages/${projection.stage_id}/failures/`)}
      empty="Validation and failure artifacts are not available yet."
    />
  </section>;
}

const repairHistoryTypes = new Set([
  "COMMAND_FAILED",
  "FAILURE_EVIDENCE_FROZEN",
  "FAILURE_CLASSIFIED",
  "REPAIR_PROPOSAL_CREATED",
  "REPAIR_REVIEW_COMPLETED",
  "REPAIR_APPLY_STARTED",
  "REPAIR_APPLY_COMPLETED",
  "REPAIR_APPLY_FAILED",
  "REPAIR_REVALIDATION_COMPLETED",
  "STAGE_VALIDATION_FAILED",
  "STAGE_VALIDATION_COMPLETED",
  "STAGE_SEALED",
]);

const repairHistoryLabels: Record<string, string> = {
  COMMAND_FAILED: "Migration command failed",
  FAILURE_EVIDENCE_FROZEN: "Failure evidence captured",
  FAILURE_CLASSIFIED: "Failure classified",
  REPAIR_PROPOSAL_CREATED: "Dependency repair proposed",
  REPAIR_REVIEW_COMPLETED: "Reviewer result recorded",
  REPAIR_APPLY_STARTED: "Approved repair started",
  REPAIR_APPLY_COMPLETED: "Repair effects applied",
  REPAIR_APPLY_FAILED: "Repair execution failed",
  REPAIR_REVALIDATION_COMPLETED: "Repair effects verified",
  STAGE_VALIDATION_FAILED: "Validation failed",
  STAGE_VALIDATION_COMPLETED: "Validation passed",
  STAGE_SEALED: "Stage sealed",
};

function HistoricalRepairHistory({ projection, workflowEvents }: Pick<SharedProps, "projection" | "workflowEvents">) {
  const groups = projection.route_stages
    .filter((stage) => stage.stage_id !== projection.stage_id)
    .map((stage) => ({
      stage,
      events: workflowEvents.filter((event) => event.stage_id === stage.stage_id && repairHistoryTypes.has(event.event_type)),
    }))
    .filter((group) => group.events.length > 0);
  if (groups.length === 0) return null;
  return <section className={styles.repairSection} aria-labelledby="transform-historical-repair">
    <h4 id="transform-historical-repair">Historical repair and validation history</h4>
    <p className={styles.note}>These events belong to completed or superseded stages. They are retained for audit and are not current blockers.</p>
    {groups.map(({ stage, events }) => <section key={stage.stage_id} className={styles.repairSection}>
      <h4>Angular {stage.source_version ?? "unavailable"} to {stage.target_version ?? "unavailable"}</h4>
      <ol className={styles.artifactList}>
        {events.map((event) => <li key={event.event_id}>
          <strong>{repairHistoryLabels[event.event_type] ?? "Historical workflow evidence"}</strong>
          <span>{displayStatus(stage.status)} · Resolved or superseded</span>
          <TechnicalDetails>
            <code>Event type: {event.event_type}</code>
            <code>Event ID: {event.event_id}</code>
            <pre className={styles.diagnostics}>{JSON.stringify(event.payload, null, 2)}</pre>
          </TechnicalDetails>
        </li>)}
      </ol>
    </section>)}
  </section>;
}

export function RepairEvidence({ projection, workflowEvents, artifacts }: SharedProps) {
  const review = projection.repair_review;
  const dependency = projection.dependency_operation;
  const isDependencyTransition = dependency?.operation === "dependency_transition";
  const validationTargets = projection.repair_contract?.validation_targets ?? [];
  const diffAvailable = Boolean(projection.repair_safe_diff && projection.repair_safe_diff.trim());
  const g10Waiting = projection.status === "waiting_gate" && projection.active_gate === "G10";
  const reviewerVerdict = review?.decision === "accept"
    ? "Accepted"
    : review?.decision === "request_changes"
      ? "Changes requested"
      : review?.decision === "reject"
        ? "Rejected"
        : null;
  return <section className={styles.card} aria-labelledby="transform-repair">
    <span className={styles.eyebrow}>08 / Governed repair</span>
    <h3 id="transform-repair">Repair workflow</h3>
    <dl className={styles.metadata}>
      <div><dt>Status</dt><dd>{displayStatus(projection.repair_status)}</dd></div>
      <div><dt>Repair approval</dt><dd>{reviewerVerdict ? "Reviewed" : "Unavailable"}</dd></div>
      <div><dt>Effects verified</dt><dd>{projection.repair_verification?.verified ? "Verified" : "Unavailable"}</dd></div>
      <div><dt>Validation after repair</dt><dd>{projection.repair_validation_checksum ? "Recorded" : "Unavailable"}</dd></div>
    </dl>
    <p className={styles.note}>Main LLM authors the proposal. Independent Reviewer evaluates it. Frontend submits only your decision; backend applies and validates the persisted proposal.</p>
    <section className={styles.repairSection} aria-labelledby="transform-repair-proposal">
      <h4 id="transform-repair-proposal">Main LLM proposal</h4>
      <dl className={styles.metadata}>
        <div><dt>Proposal evidence</dt><dd>{projection.repair_proposal_checksum ? "Recorded" : "Unavailable"}</dd></div>
        <div><dt>Repair authorization</dt><dd>{projection.repair_contract?.human_decision?.accepted ? "Accepted" : projection.repair_contract?.human_decision ? "Rejected" : "Unavailable"}</dd></div>
      </dl>
      <TechnicalDetails>
        <code>Attempt ID: {projection.repair_attempt_id ?? "unavailable"}</code>
        <code>Attempt number: {projection.repair_attempt_number ?? "unavailable"}</code>
        <code>Parent attempt: {projection.repair_parent_attempt_id ?? "unavailable"}</code>
        <code>Failed execution: {projection.repair_contract?.failure_execution_id ?? "unavailable"}</code>
        <code>Failure type: {projection.repair_contract?.failure_type ?? "unavailable"}</code>
        <code>Repair kind: {projection.repair_contract?.repair_kind ?? "unavailable"}</code>
        <code>Strategy: {projection.repair_contract?.strategy ?? "unavailable"}</code>
        <code>Risk level: {projection.repair_risk_level ?? "unavailable"}</code>
        <code>Proposal checksum: {projection.repair_proposal_checksum ?? "unavailable"}</code>
      </TechnicalDetails>
    {!isDependencyTransition ? <><h4>Repository-relative changed files</h4>
    {projection.repair_proposal_operations && projection.repair_proposal_operations.length > 0 ? <>
      <ul className={styles.artifactList}>
        {projection.repair_proposal_operations.map((item, index) => <li key={`${index}-${item.path}`}>
          <code>Operation: {item.operation ?? "unavailable"}</code>
          <code>File: {item.path ?? "unavailable"}</code>
          <code>Preimage: {item.preimage_sha256 ?? "unavailable"}</code>
          <code>Postimage: {item.postimage_sha256 ?? "pending apply"}</code>
        </li>)}
      </ul>
    </> : <p className={styles.note}>No proposed changed files are available.</p>}</> : null}
    <h4>Rationale</h4>
    {projection.repair_rationale.length > 0
      ? <ul>{projection.repair_rationale.map((item) => <li key={item}>{item}</li>)}</ul>
      : <p className={styles.note}>No proposal rationale is available.</p>}
    </section>
    {!isDependencyTransition ? <section className={styles.repairSection} aria-labelledby="transform-repair-diff">
      <h4 id="transform-repair-diff">Exact candidate diff</h4>
      <dl className={styles.metadata}>
        <div><dt>Candidate diff</dt><dd>{diffAvailable ? "Available" : "Unavailable"}</dd></div>
      </dl>
    {diffAvailable
      ? <UnifiedDiffViewer content={projection.repair_safe_diff!} />
      : projection.repair_attempt_id
        ? <div className={styles.alert} role="alert">
            <p>Candidate diff is empty or unavailable. Repair approval is disabled.</p>
            {g10Waiting ? <p>The backend cannot bind an empty diff into the repair approval package; the repair proposal must be revised before approval.</p> : null}
          </div>
        : null}
    {!diffAvailable && !projection.repair_attempt_id ? <p className={styles.note}>No repair candidate diff is available.</p> : null}
    </section> : null}
    {dependency?.operation === "dependency_transition" ? <section className={styles.repairSection} aria-labelledby="transform-dependency-operation">
      <h4 id="transform-dependency-operation">Dependency Transition Plan</h4>
      <dl className={styles.metadata}>
        <div><dt>Blocking dependency</dt><dd>{dependency.blocking_dependency.package}@{dependency.blocking_dependency.installed_version}</dd></div>
        <div><dt>Target exact package</dt><dd>{dependency.target_state.package}@{dependency.target_state.target_version}</dd></div>
        <div><dt>Target Angular major</dt><dd>{dependency.target_state.angular_major}</dd></div>
        <div><dt>Strategy</dt><dd>{dependency.strategy}</dd></div>
        <div><dt>Checkpoint authority</dt><dd>{dependency.checkpoint_id}</dd></div>
        <div><dt>Workspace authority</dt><dd>{projection.workspace_fingerprint ? "Bound" : "Unavailable"}</dd></div>
        <div><dt>Proposal evidence</dt><dd>{projection.repair_proposal_checksum ? "Recorded" : "Unavailable"}</dd></div>
      <div><dt>Reviewer verdict</dt><dd>{reviewerVerdict ?? "pending"}</dd></div>
      </dl>
      <TechnicalDetails>
        <code>Checkpoint ID: {dependency.checkpoint_id}</code>
        <code>Workspace fingerprint: {projection.workspace_fingerprint ?? "unavailable"}</code>
        <code>Proposal checksum: {projection.repair_proposal_checksum ?? "unavailable"}</code>
      </TechnicalDetails>
      <h4>Conflicting peer authority</h4>
      <ul>{dependency.blocking_dependency.required_peer_ranges.map((peer) => <li key={peer.package}><code>{peer.package}: {peer.version_range}</code></li>)}</ul>
      <h4>Ordered phases</h4>
      <ol>
        <li>Uninstall <code>{dependency.blocking_dependency.package}</code>.</li>
        <li>Run the authorized Angular {dependency.target_state.angular_major} update.</li>
        <li>Reinstall exact <code>{dependency.target_state.package}@{dependency.target_state.target_version}</code>.</li>
        <li>Run <code>npm ci</code>.</li>
        <li>Verify dependency closure.</li>
      </ol>
      <h4>Validation targets</h4>
      {validationTargets.length > 0
        ? <ul>{validationTargets.map((target) => <li key={target}>{target}</li>)}</ul>
        : <p className={styles.note}>Validation targets are pending Reviewer binding.</p>}
    </section> : null}
    {dependency?.operation === "dependency_add" ? <section className={styles.repairSection} aria-labelledby="transform-dependency-addition">
      <h4 id="transform-dependency-addition">Dependency Addition</h4>
      <dl className={styles.metadata}>
        <div><dt>Package</dt><dd>{dependency.package ?? "unavailable"}</dd></div>
        <div><dt>Section</dt><dd>{dependency.section ?? "unavailable"}</dd></div>
        <div><dt>Exact version</dt><dd>{dependency.new_version ?? "unavailable"}</dd></div>
        <div><dt>Strategy</dt><dd>{dependency.strategy ?? "unavailable"}</dd></div>
        <div><dt>Proposal evidence</dt><dd>{projection.repair_proposal_checksum ? "Recorded" : "Unavailable"}</dd></div>
      <div><dt>Reviewer verdict</dt><dd>{reviewerVerdict ?? "pending"}</dd></div>
      </dl>
      <TechnicalDetails>
        <code>Operation: {dependency.operation}</code>
        <code>Path: {dependency.path ?? "unavailable"}</code>
        <code>Provenance: {dependency.provenance && dependency.provenance.length > 0 ? JSON.stringify(dependency.provenance) : "not projected"}</code>
        <code>Workspace fingerprint: {projection.workspace_fingerprint ?? "unavailable"}</code>
      </TechnicalDetails>
    </section> : null}
    {dependency && dependency.operation !== "dependency_transition" && dependency.operation !== "dependency_add"
      ? <p className={styles.note}>Dependency operation details unavailable</p>
      : null}
    <section className={styles.repairSection} aria-labelledby="transform-repair-review">
      <h4 id="transform-repair-review">Independent Reviewer</h4>
      {review ? <>
      <dl className={styles.metadata}>
        <div><dt>Verdict</dt><dd>{reviewerVerdict}</dd></div>
        <div><dt>Risk assessment</dt><dd>{review.risk_assessment || "not available"}</dd></div>
        <div><dt>Review evidence</dt><dd>{projection.repair_review_checksum ? "Recorded" : "Unavailable"}</dd></div>
      </dl>
      <h4>Findings</h4>
      {review.findings.length > 0 ? <ul>{review.findings.map((item) => <li key={item}>{item}</li>)}</ul> : <p className={styles.note}>No Reviewer findings.</p>}
      <h4>Policy checks</h4>
      {review.policy_checks.length > 0 ? <ul>{review.policy_checks.map((item) => <li key={item}>{item}</li>)}</ul> : <p className={styles.note}>No policy checks reported.</p>}
      <h4>Limitations</h4>
      {review.limitations.length > 0 ? <ul>{review.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p className={styles.note}>No Reviewer limitations reported.</p>}
      </> : <p className={styles.note}>Reviewer result is not available yet.</p>}
    </section>
    <section className={styles.repairSection} aria-labelledby="transform-repair-validation-targets">
      <h4 id="transform-repair-validation-targets">Validation expected after Apply</h4>
      {review
        ? review.required_validation_targets.length > 0
          ? <ul>{review.required_validation_targets.map((target) => <li key={target}>{target}</li>)}</ul>
          : <p className={styles.note}>No validation targets returned.</p>
        : <p className={styles.note}>Validation targets are not available until Reviewer result is returned.</p>}
    </section>
    <TechnicalDetails>
      <code>Repair attempt ID: {projection.repair_attempt_id ?? "unavailable"}</code>
      <code>Proposal checksum: {projection.repair_proposal_checksum ?? "unavailable"}</code>
      <code>Review checksum: {projection.repair_review_checksum ?? "unavailable"}</code>
      <code>Apply ledger checksum: {projection.repair_apply_checksum ?? "unavailable"}</code>
      <code>Validation checksum: {projection.repair_validation_checksum ?? "unavailable"}</code>
    </TechnicalDetails>
    <EvidenceLinks
      artifacts={artifacts}
      matches={(path) => path.includes("05_repairs/")}
      empty="No governed repair artifacts are available."
      activeAttemptId={projection.repair_attempt_id}
    />
    {isDependencyTransition && projection.completed_transition_phases.length > 0 ? <section className={styles.repairSection} aria-labelledby="transform-transition-phases">
      <h4 id="transform-transition-phases">Persisted Dependency Transition Results</h4>
      {projection.completed_transition_phases.map((phase, index) => <section key={`${phase.phase}-${phase.execution_id ?? phase.artifact_id ?? index}`} className={styles.repairSection}>
        <h4>{phase.phase}: {displayStatus(phase.status)}</h4>
        <TechnicalDetails>
          <code>Execution ID: {phase.execution_id ?? "not applicable"}</code>
          <code>Evidence ID: {phase.artifact_id ?? "unavailable"}</code>
        </TechnicalDetails>
        {phase.package_json_change ? <>
          <dl className={styles.metadata}>
            <div><dt>Manifest change</dt><dd>{phase.package_json_change.unified_diff ? "Recorded" : "Unavailable"}</dd></div>
          </dl>
          <TechnicalDetails>
            <code>package.json before: {phase.package_json_change.before_checksum ?? "unavailable"}</code>
            <code>package.json after: {phase.package_json_change.after_checksum ?? "unavailable"}</code>
          </TechnicalDetails>
          {phase.package_json_change.unified_diff
            ? <UnifiedDiffViewer content={phase.package_json_change.unified_diff} />
            : <p className={styles.note}>The persisted verification predates manifest diff capture.</p>}
        </> : null}
        {phase.lockfile_changes ? <>
          <h4>Exact package-lock.json dependency changes</h4>
          <pre className={styles.diagnostics}>{JSON.stringify(phase.lockfile_changes, null, 2)}</pre>
        </> : null}
        {phase.installed_verification ? <>
          <h4>Installed package verification</h4>
          <pre className={styles.diagnostics}>{JSON.stringify(phase.installed_verification, null, 2)}</pre>
        </> : null}
      </section>)}
      <dl className={styles.metadata}>
        <div><dt>npm-ci result</dt><dd>{projection.validation_results.npm_ci?.command_status ?? "pending"}</dd></div>
        <div><dt>Dependency closure</dt><dd>{projection.dependency_closure ? "persisted" : "pending"}</dd></div>
        <div><dt>Angular retry result</dt><dd>{projection.angular_update_retry_status ?? "pending"}</dd></div>
      </dl>
    </section> : null}
    {projection.repair_verification ? <section className={styles.repairSection} aria-labelledby="transform-repair-verification">
      <h4 id="transform-repair-verification">Repair post-state verification</h4>
      <dl className={styles.metadata}>
        <div><dt>Applied and verified</dt><dd>{projection.repair_verification.verified ? "Verified" : "Unavailable"}</dd></div>
      </dl>
      <TechnicalDetails>
        <code>Preimage fingerprint: {projection.repair_verification.pre_fingerprint ?? "unavailable"}</code>
        <code>Postimage fingerprint: {projection.repair_verification.post_fingerprint ?? "unavailable"}</code>
      </TechnicalDetails>
    </section> : null}
    <HistoricalRepairHistory projection={projection} workflowEvents={workflowEvents} />
  </section>;
}

export function SealAndRoute({ projection, workflowEvents, artifacts }: SharedProps) {
  const isSealed = projection.stage_status.toLowerCase() === "sealed";
  return <section className={`${styles.card} ${styles.cardWide}`} aria-labelledby="transform-seal">
    <span className={styles.eyebrow}>09 / Seal and route continuation</span>
    <h3 id="transform-seal">Stage seal and next-stage lineage</h3>
    <dl className={styles.metadata}>
      <div><dt>Seal status</dt><dd>{isSealed ? "Sealed" : displayStatus(projection.stage_status)}</dd></div>
      <div><dt>Next-stage input</dt><dd>{isSealed ? "Available from sealed output" : "Unavailable until seal"}</dd></div>
      <div><dt>Dependency closure</dt><dd>{projection.dependency_closure ? "Recorded" : "Unavailable"}</dd></div>
      <div><dt>Current workspace</dt><dd>{projection.workspace_fingerprint ? "Fingerprint recorded" : "Unavailable"}</dd></div>
    </dl>
    <h4>Stage validation results</h4>
    <dl className={styles.metadata}>
      {Object.entries(projection.validation_results).map(([name, result]) => <div key={name}>
        <dt>{name === "npm_ci" ? "Install" : name === "build" ? "Production build" : name === "test" ? "Tests" : name}</dt><dd>{displayStatus(result.status)} / {displayStatus(result.command_status)}</dd>
      </div>)}
    </dl>
    <ol className={styles.route}>
      {projection.route_stages.map((stage) => <li key={stage.stage_id}>
        <strong>Angular {stage.source_version ?? "source"} to {stage.target_version ?? "target"}</strong>
        <span>{displayStatus(stage.status)}{stage.stage_id === projection.stage_id ? " · Active stage" : ""}</span>
      </li>)}
    </ol>
    <p className={styles.note}>Per-stage seal manifest and final fingerprint lineage are not separately projected by the current API. The UI leaves them unavailable instead of inferring them from event text.</p>
    <TechnicalDetails>
      <code>Sealed manifest checksum: {isSealed ? projection.sealed_chain_hash ?? "unavailable" : "not sealed for active stage"}</code>
      <code>Current workspace fingerprint: {projection.workspace_fingerprint ?? "unavailable"}</code>
      <code>Seal event evidence: {workflowEvents.some((event) => event.stage_id === projection.stage_id && event.event_type === "STAGE_SEALED") ? "recorded" : "unavailable"}</code>
    </TechnicalDetails>
    <EvidenceLinks
      artifacts={artifacts}
      matches={(path) => path.includes(`/stages/${projection.stage_id}/seal/`)}
      empty="Seal evidence is not available yet."
    />
  </section>;
}
