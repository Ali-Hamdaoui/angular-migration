import type { ArtifactRefDto, WorkflowEventDto } from "@/types/generated/api";
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
};

const transformerEvents = new Set<string>(TRANSFORMATION_EVENT_TYPES);
const transformationEvent = (event: WorkflowEventDto) => transformerEvents.has(event.event_type);

function latest(events: WorkflowEventDto[], matches: (type: string) => boolean) {
  return events.filter((event) => matches(event.event_type)).at(-1);
}

function eventName(event: WorkflowEventDto | undefined, empty: string) {
  return event?.event_type.replaceAll("_", " ").toLowerCase() ?? empty;
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
        <code>{artifact.checksum}</code>
        {historical ? <small className={styles.historical}>historical attempt artifact</small> : null}
      </li>;
    })}
  </ul>;
}

export function StageSummary({ projection, workflowEvents }: Omit<SharedProps, "artifacts">) {
  const workspace = latest(workflowEvents, (type) =>
    type === "STAGE_INPUT_CHECKPOINT_CREATED"
    || type === "STAGE_WORKSPACE_RECONSTRUCTED"
    || type === "STAGE_WORKSPACE_FINGERPRINT_MISMATCH",
  );
  const preflight = latest(workflowEvents, (type) => type.startsWith("COMPATIBILITY_PREFLIGHT_"));
  return <section className={styles.card} aria-labelledby="transform-stage-summary">
    <span className={styles.eyebrow}>01 / Stage and continuation</span>
    <h3 id="transform-stage-summary">Exact migration stage</h3>
    <dl className={styles.metadata}>
      <div><dt>Stage</dt><dd>{projection.stage_id}</dd></div>
      <div><dt>Angular route</dt><dd>{projection.source_version ?? "unavailable"} → {projection.target_version ?? "unavailable"}</dd></div>
      <div><dt>Stage status</dt><dd>{projection.stage_status}</dd></div>
      <div><dt>Continuation</dt><dd>{projection.status}</dd></div>
      <div><dt>Current step</dt><dd>{projection.workflow_step}</dd></div>
      <div><dt>State version</dt><dd>{projection.state_version}</dd></div>
      <div><dt>Workspace</dt><dd>{eventName(workspace, "preparation not recorded")}</dd></div>
      <div><dt>Compatibility</dt><dd>{eventName(preflight, "preflight not recorded")}</dd></div>
    </dl>
    <p className={styles.fingerprint}>Fingerprint: {projection.workspace_fingerprint ?? "not available"}</p>
  </section>;
}

export function WorkerStatus({ projection }: { projection: TransformationProjection }) {
  return <section className={styles.card} aria-labelledby="transform-worker-status">
    <span className={styles.eyebrow}>02 / Worker and command</span>
    <h3 id="transform-worker-status">Durable execution</h3>
    <dl className={styles.metadata}>
      <div><dt>Continuation ID</dt><dd>{projection.continuation_id}</dd></div>
      <div><dt>Worker state</dt><dd>{projection.status}</dd></div>
      <div><dt>Command ID</dt><dd>{projection.active_command_id ?? "none"}</dd></div>
      <div><dt>Command state</dt><dd>{projection.active_command_status ?? "none"}</dd></div>
      <div><dt>Command phase</dt><dd>{projection.active_command_phase ?? "none"}</dd></div>
      <div><dt>Checkpoint</dt><dd>{projection.checkpoint_kind ?? "none"}</dd></div>
      <div><dt>Cancellation</dt><dd>{projection.cancel_requested_at ?? "not requested"}</dd></div>
    </dl>
  </section>;
}

export function LogsAndDiagnostics({ projection, workflowEvents }: Omit<SharedProps, "artifacts">) {
  const diagnostic = latest(workflowEvents.filter(transformationEvent), () => true);
  const historicalDiagnostic = Boolean(
    diagnostic
    && !projection.active_error
    && /(?:FAILED|BLOCKED|MISMATCH|STALE)/.test(diagnostic.event_type),
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
        Latest workflow evidence{historicalDiagnostic ? " (historical/resolved)" : ""}: {diagnostic.event_type}
      </p>
      {Object.keys(diagnostic.payload).length > 0
        ? <pre className={styles.diagnostics}>{JSON.stringify(diagnostic.payload, null, 2)}</pre>
        : null}
    </> : null}
    {projection.active_error ? <div className={styles.alert} role="alert">
      <p>Current blocker: {projection.active_error.code}</p>
      {projection.active_error.message ? <p>{projection.active_error.message}</p> : null}
      {projection.runtime_profile_binding
        ? <pre className={styles.diagnostics}>{JSON.stringify(projection.runtime_profile_binding, null, 2)}</pre>
        : null}
    </div> : null}
    {projection.historical_diagnostics.map((item) => <div key={`${item.code}-${item.message}`} className={styles.note}>
      <strong>Historical/resolved: {item.code}</strong>
      {item.message ? <p>{item.message}</p> : null}
    </div>)}
  </section>;
}

export function TransformationEvidence({ projection, workflowEvents, artifacts }: SharedProps) {
  const version = latest(workflowEvents, (type) => type.startsWith("VERSION_VERIFICATION_"));
  const completed = latest(workflowEvents, (type) => type === "STAGE_TRANSFORMATION_COMPLETED");
  return <section className={styles.card} aria-labelledby="transform-evidence">
    <span className={styles.eyebrow}>06 / Version and transformation evidence</span>
    <h3 id="transform-evidence">Target proof and changed files</h3>
    <dl className={styles.metadata}>
      <div><dt>Four-source proof</dt><dd>{eventName(version, "not recorded")}</dd></div>
      <div><dt>Transformation</dt><dd>{eventName(completed, "not completed")}</dd></div>
      <div><dt>G08</dt><dd>{eventName(latest(workflowEvents, (type) => type.startsWith("G08_")), "not created")}</dd></div>
    </dl>
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
      <div><dt>Install/build/test/lint</dt><dd>{eventName(validation, "not started")}</dd></div>
      <div><dt>G11 decision</dt><dd>{eventName(latest(workflowEvents, (type) => type.startsWith("G11_")), "not created")}</dd></div>
      <div><dt>Failure evidence</dt><dd>{eventName(latest(workflowEvents, (type) => type === "FAILURE_EVIDENCE_FROZEN"), "none")}</dd></div>
      <div><dt>Classification</dt><dd>{eventName(latest(workflowEvents, (type) => type === "FAILURE_CLASSIFIED"), "none")}</dd></div>
    </dl>
    <EvidenceLinks
      artifacts={artifacts}
      matches={(path) =>
        path.includes(`/stages/${projection.stage_id}/validation/`)
        || path.includes(`/stages/${projection.stage_id}/failures/`)}
      empty="Validation and failure artifacts are not available yet."
    />
  </section>;
}

export function RepairEvidence({ projection, workflowEvents, artifacts }: SharedProps) {
  const review = projection.repair_review;
  const dependency = projection.dependency_operation;
  const isDependencyTransition = Boolean(dependency);
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
    <h3 id="transform-repair">G10 repair review</h3>
    <dl className={styles.metadata}>
      <div><dt>Status</dt><dd>{projection.repair_status ?? "not required"}</dd></div>
      <div><dt>G10</dt><dd>{eventName(latest(workflowEvents, (type) => type.startsWith("G10_")), "not created")}</dd></div>
      <div><dt>Apply ledger</dt><dd>{projection.repair_apply_checksum ?? "not applied"}</dd></div>
      <div><dt>G11 revalidation</dt><dd>{projection.repair_validation_checksum ?? "pending"}</dd></div>
    </dl>
    <p className={styles.note}>Main LLM authors the proposal. Independent Reviewer evaluates it. Frontend submits only your decision; backend applies and validates the persisted proposal.</p>
    <section className={styles.repairSection} aria-labelledby="transform-repair-proposal">
      <h4 id="transform-repair-proposal">Main LLM proposal</h4>
      <dl className={styles.metadata}>
        <div><dt>Attempt ID</dt><dd>{projection.repair_attempt_id ?? "none"}</dd></div>
        <div><dt>Attempt number</dt><dd>{projection.repair_attempt_number ?? "not available"}</dd></div>
        <div><dt>Parent attempt</dt><dd>{projection.repair_parent_attempt_id ?? "none"}</dd></div>
        <div><dt>Failed execution</dt><dd>{projection.repair_contract?.failure_execution_id ?? "unavailable"}</dd></div>
        <div><dt>Failure type</dt><dd>{projection.repair_contract?.failure_type ?? "unavailable"}</dd></div>
        <div><dt>Repair kind</dt><dd>{projection.repair_contract?.repair_kind ?? "unavailable"}</dd></div>
        <div><dt>Strategy</dt><dd>{projection.repair_contract?.strategy ?? "unavailable"}</dd></div>
        <div><dt>Risk level</dt><dd>{projection.repair_risk_level ?? "not available"}</dd></div>
        <div><dt>Proposal checksum</dt><dd>{projection.repair_proposal_checksum ?? "unavailable"}</dd></div>
        <div><dt>Human decision</dt><dd>{projection.repair_contract?.human_decision?.decision ?? "pending"}</dd></div>
      </dl>
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
        <div><dt>Diff checksum</dt><dd>{projection.repair_diff_checksum ?? "unavailable"}</dd></div>
      </dl>
    {diffAvailable
      ? <UnifiedDiffViewer content={projection.repair_safe_diff!} />
      : projection.repair_attempt_id
        ? <div className={styles.alert} role="alert">
            <p>Candidate diff is empty or unavailable — G10 approval disabled.</p>
            {g10Waiting ? <p>The backend cannot bind an empty diff into the G10 package; the repair proposal must be revised before approval.</p> : null}
          </div>
        : null}
    {!diffAvailable && !projection.repair_attempt_id ? <p className={styles.note}>No repair candidate diff is available.</p> : null}
    </section> : null}
    {dependency ? <section className={styles.repairSection} aria-labelledby="transform-dependency-operation">
      <h4 id="transform-dependency-operation">Dependency Transition Plan</h4>
      <dl className={styles.metadata}>
        <div><dt>Blocking dependency</dt><dd>{dependency.blocking_dependency.package}@{dependency.blocking_dependency.installed_version}</dd></div>
        <div><dt>Target exact package</dt><dd>{dependency.target_state.package}@{dependency.target_state.target_version}</dd></div>
        <div><dt>Target Angular major</dt><dd>{dependency.target_state.angular_major}</dd></div>
        <div><dt>Strategy</dt><dd>{dependency.strategy}</dd></div>
        <div><dt>Checkpoint authority</dt><dd>{dependency.checkpoint_id}</dd></div>
        <div><dt>Workspace authority</dt><dd>{projection.workspace_fingerprint ?? "unavailable"}</dd></div>
        <div><dt>Proposal checksum</dt><dd>{projection.repair_proposal_checksum ?? "unavailable"}</dd></div>
        <div><dt>Reviewer verdict</dt><dd>{reviewerVerdict ?? "pending"}</dd></div>
      </dl>
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
    <section className={styles.repairSection} aria-labelledby="transform-repair-review">
      <h4 id="transform-repair-review">Independent Reviewer</h4>
      {review ? <>
      <dl className={styles.metadata}>
        <div><dt>Verdict</dt><dd>{reviewerVerdict}</dd></div>
        <div><dt>Risk assessment</dt><dd>{review.risk_assessment || "not available"}</dd></div>
        <div><dt>Review checksum</dt><dd>{projection.repair_review_checksum ?? "unavailable"}</dd></div>
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
    <EvidenceLinks
      artifacts={artifacts}
      matches={(path) => path.includes("05_repairs/")}
      empty="No governed repair artifacts are available."
      activeAttemptId={projection.repair_attempt_id}
    />
    {isDependencyTransition && projection.completed_transition_phases.length > 0 ? <section className={styles.repairSection} aria-labelledby="transform-transition-phases">
      <h4 id="transform-transition-phases">Persisted Dependency Transition Results</h4>
      {projection.completed_transition_phases.map((phase, index) => <section key={`${phase.phase}-${phase.execution_id ?? phase.artifact_id ?? index}`} className={styles.repairSection}>
        <h4>{phase.phase}: {phase.status}</h4>
        <p>{phase.execution_id ? <>Execution <code>{phase.execution_id}</code></> : <>Execution ID not applicable</>}{phase.artifact_id ? <> / Evidence <code>{phase.artifact_id}</code></> : null}</p>
        {phase.package_json_change ? <>
          <dl className={styles.metadata}>
            <div><dt>package.json before</dt><dd>{phase.package_json_change.before_checksum ?? "unavailable"}</dd></div>
            <div><dt>package.json after</dt><dd>{phase.package_json_change.after_checksum ?? "unavailable"}</dd></div>
          </dl>
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
        <div><dt>Applied and verified</dt><dd>{projection.repair_verification.verified ? "yes" : "pending"}</dd></div>
        <div><dt>Preimage state</dt><dd>{projection.repair_verification.pre_fingerprint ?? "unavailable"}</dd></div>
        <div><dt>Postimage state</dt><dd>{projection.repair_verification.post_fingerprint ?? "unavailable"}</dd></div>
      </dl>
    </section> : null}
  </section>;
}

export function SealAndRoute({ projection, workflowEvents, artifacts }: SharedProps) {
  const completion = latest(workflowEvents, (type) => type === "STAGED_MIGRATION_COMPLETED");
  return <section className={`${styles.card} ${styles.cardWide}`} aria-labelledby="transform-seal">
    <span className={styles.eyebrow}>09 / Seal and route continuation</span>
    <h3 id="transform-seal">Approved migration route</h3>
    <dl className={styles.metadata}>
      <div><dt>G11 stage approval</dt><dd>{eventName(latest(workflowEvents, (type) => type.startsWith("G11_")), "not created")}</dd></div>
      <div><dt>Latest seal</dt><dd>{projection.sealed_chain_hash ?? "not sealed"}</dd></div>
      <div><dt>Next stage</dt><dd>{eventName(latest(workflowEvents, (type) => type === "NEXT_STAGE_MATERIALIZED"), "not materialized")}</dd></div>
      <div><dt>Full migration</dt><dd>{eventName(completion, "not completed")}</dd></div>
      <div><dt>Angular retry</dt><dd>{projection.angular_update_retry_status ?? "not required"}</dd></div>
      <div><dt>Dependency closure</dt><dd>{projection.dependency_closure ? "verified" : "pending"}</dd></div>
    </dl>
    <h4>Stage validation results</h4>
    <dl className={styles.metadata}>
      {Object.entries(projection.validation_results).map(([name, result]) => <div key={name}>
        <dt>{name}</dt><dd>{result.status} / {result.command_status ?? "not run"}{result.execution_id ? ` / ${result.execution_id}` : ""}</dd>
      </div>)}
    </dl>
    <ol className={styles.route}>
      {projection.route_stages.map((stage) => <li key={stage.stage_id}>
        <strong>{stage.source_version ?? "source"} → {stage.target_version ?? "target"}: {stage.status}</strong>
        <code>{stage.stage_id}</code>
      </li>)}
    </ol>
    <EvidenceLinks
      artifacts={artifacts}
      matches={(path) => path.includes(`/stages/${projection.stage_id}/seal/`)}
      empty="Seal evidence is not available yet."
    />
  </section>;
}
