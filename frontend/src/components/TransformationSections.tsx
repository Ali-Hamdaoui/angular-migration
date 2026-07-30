import type { ArtifactRefDto, WorkflowEventDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";
import { getBackendBaseUrl } from "@/api/client";
import { TRANSFORMATION_EVENT_TYPES } from "@/hooks/useAuthoritativeRun";
import { LiveCommandLogViewer } from "@/components/LogViewer";
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

function EvidenceLinks({
  artifacts,
  matches,
  empty,
}: {
  artifacts: ArtifactRefDto[];
  matches: (path: string) => boolean;
  empty: string;
}) {
  const visible = artifacts.filter((artifact) => matches(artifact.relative_path));
  if (visible.length === 0) return <p className={styles.note}>{empty}</p>;
  return <ul className={styles.artifactList}>
    {visible.map((artifact) => <li key={artifact.artifact_id}>
      <a
        href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`}
        target="_blank"
        rel="noreferrer"
      >
        {artifact.relative_path}
      </a>
      <code>{artifact.checksum}</code>
    </li>)}
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
      <div><dt>Current step</dt><dd>{projection.current_node}</dd></div>
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
      <div><dt>Checkpoint</dt><dd>{projection.checkpoint_kind ?? "none"}</dd></div>
      <div><dt>Cancellation</dt><dd>{projection.cancel_requested_at ?? "not requested"}</dd></div>
    </dl>
  </section>;
}

export function LogsAndDiagnostics({ projection, workflowEvents }: Omit<SharedProps, "artifacts">) {
  const diagnostic = latest(workflowEvents.filter(transformationEvent), () => true);
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
      <p className={styles.event}>Latest workflow evidence: {diagnostic.event_type}</p>
      {Object.keys(diagnostic.payload).length > 0
        ? <pre className={styles.diagnostics}>{JSON.stringify(diagnostic.payload, null, 2)}</pre>
        : null}
    </> : null}
    {projection.last_error_code ? <div className={styles.alert} role="alert">
      <p>Backend error: {projection.last_error_code}</p>
      {projection.last_error_message ? <p>{projection.last_error_message}</p> : null}
      {projection.runtime_profile_binding
        ? <pre className={styles.diagnostics}>{JSON.stringify(projection.runtime_profile_binding, null, 2)}</pre>
        : null}
    </div> : null}
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
      <div><dt>G09 decision</dt><dd>{eventName(latest(workflowEvents, (type) => type.startsWith("G09_")), "not created")}</dd></div>
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
  return <section className={styles.card} aria-labelledby="transform-repair">
    <span className={styles.eyebrow}>08 / Governed repair</span>
    <h3 id="transform-repair">Proposal, review, and revalidation</h3>
    <dl className={styles.metadata}>
      <div><dt>Attempt</dt><dd>{projection.repair_attempt_id ?? "none"}</dd></div>
      <div><dt>Status</dt><dd>{projection.repair_status ?? "not required"}</dd></div>
      <div><dt>Risk</dt><dd>{projection.repair_risk_level ?? "not available"}</dd></div>
      <div><dt>Proposal</dt><dd>{projection.repair_proposal_checksum ?? "pending"}</dd></div>
      <div><dt>Reviewer</dt><dd>{projection.repair_review_checksum ?? "pending"}</dd></div>
      <div><dt>G10</dt><dd>{eventName(latest(workflowEvents, (type) => type.startsWith("G10_")), "not created")}</dd></div>
      <div><dt>Apply ledger</dt><dd>{projection.repair_apply_checksum ?? "not applied"}</dd></div>
      <div><dt>G11 revalidation</dt><dd>{projection.repair_validation_checksum ?? "pending"}</dd></div>
    </dl>
    <EvidenceLinks
      artifacts={artifacts}
      matches={(path) => path.includes("05_repairs/")}
      empty="No governed repair artifacts are available."
    />
  </section>;
}

export function SealAndRoute({ projection, workflowEvents, artifacts }: SharedProps) {
  const completion = latest(workflowEvents, (type) => type === "STAGED_MIGRATION_COMPLETED");
  return <section className={`${styles.card} ${styles.cardWide}`} aria-labelledby="transform-seal">
    <span className={styles.eyebrow}>09 / Seal and route continuation</span>
    <h3 id="transform-seal">Approved migration route</h3>
    <dl className={styles.metadata}>
      <div><dt>G12</dt><dd>{eventName(latest(workflowEvents, (type) => type.startsWith("G12_")), "not created")}</dd></div>
      <div><dt>Latest seal</dt><dd>{projection.sealed_chain_hash ?? "not sealed"}</dd></div>
      <div><dt>Next stage</dt><dd>{eventName(latest(workflowEvents, (type) => type === "NEXT_STAGE_MATERIALIZED"), "not materialized")}</dd></div>
      <div><dt>Full migration</dt><dd>{eventName(completion, "not completed")}</dd></div>
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
