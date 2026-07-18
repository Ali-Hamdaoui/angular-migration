"use client";

import { useEffect, useMemo, useState } from "react";
import { createSourceSnapshot, getSourceSnapshot } from "@/api/snapshots";
import { getBackendBaseUrl } from "@/api/client";
import type {
  AuthoritativeRunStateDto,
  SourceSnapshotDto,
  WorkflowEventDto,
} from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

function eventSnapshotId(event: WorkflowEventDto | undefined): string | null {
  const value = event?.payload.snapshot_id;
  return typeof value === "string" ? value : null;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function SourceSnapshotPanel({
  runId,
  initialState,
}: {
  runId: string;
  initialState: AuthoritativeRunStateDto;
}) {
  const [snapshot, setSnapshot] = useState<SourceSnapshotDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const latestSnapshotEvent = useMemo(
    () =>
      [...initialState.workflow_events]
        .reverse()
        .find((event) =>
          ["SNAPSHOT_STARTED", "SNAPSHOT_CREATED", "SNAPSHOT_FAILED"].includes(event.event_type),
        ),
    [initialState.workflow_events],
  );
  const snapshotId = eventSnapshotId(latestSnapshotEvent);

  useEffect(() => {
    if (!snapshotId) return;
    setLoading(true);
    getSourceSnapshot(runId, snapshotId)
      .then(setSnapshot)
      .catch(() => setError("Snapshot details could not be loaded."))
      .finally(() => setLoading(false));
  }, [runId, snapshotId]);

  async function handleCreate() {
    setCreating(true);
    setError(null);
    try {
      const result = await createSourceSnapshot(runId, {
        expected_state_version: initialState.state_version,
        idempotency_key: `snapshot-${runId}-${Date.now()}`,
        actor: "control-tower",
      });
      setSnapshot(result);
    } catch {
      setError("The source snapshot could not be created. Refresh the run state and retry.");
    } finally {
      setCreating(false);
    }
  }

  const canCreate =
    !snapshot &&
    (initialState.status === "CREATED" || initialState.status === "SOURCE_VALIDATION_RUNNING");

  return (
    <section className={styles.panel} aria-label="Immutable source snapshot">
      <div className={styles.previewHeader}>
        <div>
          <p className={styles.kicker}>S1-F07</p>
          <h2>Immutable source snapshot</h2>
        </div>
        {canCreate ? (
          <button type="button" onClick={handleCreate} disabled={creating}>
            {creating ? "Creating snapshot..." : "Create source snapshot"}
          </button>
        ) : null}
      </div>

      {loading ? <p className={styles.note}>Loading snapshot evidence...</p> : null}
      {!snapshot && latestSnapshotEvent?.event_type === "SNAPSHOT_STARTED" ? (
        <p className={styles.note}>Snapshot acquisition is running. Evidence will appear when the backend finalizes the copy.</p>
      ) : null}
      {!snapshot && latestSnapshotEvent?.event_type === "SNAPSHOT_FAILED" ? (
        <p role="alert">Snapshot creation failed. Review the run event and retry after resolving the reported issue.</p>
      ) : null}
      {!snapshot && !latestSnapshotEvent && !loading ? (
        <p className={styles.note}>No source snapshot has been created for this run.</p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}

      {snapshot ? (
        <>
          <div className={styles.dimensionGrid} aria-label="Snapshot summary">
            <div><span>Status</span><strong>{snapshot.status}</strong></div>
            <div><span>Files</span><strong>{snapshot.file_count}</strong></div>
            <div><span>Size</span><strong>{formatBytes(snapshot.total_size_bytes)}</strong></div>
            <div><span>Policy</span><strong>{snapshot.policy_version}</strong></div>
          </div>
          <dl className={styles.metadataGrid}>
            <div><dt>Snapshot ID</dt><dd>{snapshot.snapshot_id}</dd></div>
            <div><dt>Manifest</dt><dd>{snapshot.manifest_id ?? "Unavailable"}</dd></div>
            <div><dt>Fingerprint</dt><dd>{snapshot.fingerprint ?? "Unavailable"}</dd></div>
            <div><dt>Source</dt><dd>{snapshot.source_path}</dd></div>
          </dl>
          <p className={styles.note}>Excluded paths: {snapshot.exclusions.length ? snapshot.exclusions.map((item) => item.relative_path).join(", ") : "none"}</p>
          <ul className={styles.list}>
            {snapshot.artifacts.map((artifact) => (
              <li key={artifact.artifact_id}>
                <a className={styles.actionLink} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`}>
                  {artifact.relative_path}
                </a>
                <code>{artifact.checksum}</code>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
