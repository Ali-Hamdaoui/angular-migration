"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getStageSeal, startCopyForward, submitG12Decision, submitStageSealRequest } from "@/api/stageSeal";
import type { G12Decision, SealCompletenessCheck } from "@/types/stageSeal";
import styles from "./ControlTowerShell.module.css";

type ConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";

const checkEmojis: Record<string, string> = { passed: "✓", failed: "✗", warning: "!", skipped: "-" };

function statusLabel(value: string) { return value.replaceAll("_", " "); }

export function StageSealPanel({
  runId, stageId, stateVersion, connectionStatus,
}: {
  runId: string; stageId: string; stateVersion: number; connectionStatus: ConnectionStatus;
}) {
  const [seal, setSeal] = useState<{
    seal_id: string; status: string; completeness: { status: string; checks: SealCompletenessCheck[] };
    fingerprint: { fingerprint: string; algorithm: string; asset_count: number; total_size_bytes: number; created_at: string } | null;
    copy_forward: { status: string; source_stage_id: string | null; target_stage_id: string | null; copied_artifact_count: number | null; copied_artifact_ids: string[]; detail: string | null } | null;
    artifact_ids: string[]; artifact_checksums: Record<string, string>; g12_decision: G12Decision | null;
    state_version: number; event_sequence: number; idempotent_replay: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const result = await getStageSeal(runId, stageId);
      setSeal(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setSeal(null);
      } else {
        setError("Stage seal data could not be loaded.");
      }
    } finally { setLoading(false); }
  }, [runId, stageId]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion]);
  useEffect(() => {
    if (seal?.status === "pending_approval" || seal?.copy_forward?.status === "running") {
      const timer = window.setInterval(() => void refresh(), 2000);
      return () => window.clearInterval(timer);
    }
  }, [refresh, seal?.status, seal?.copy_forward?.status]);

  async function handleSeal() {
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await submitStageSealRequest(runId, stageId, {
        expected_state_version: stateVersion,
        idempotency_key: `stage-seal-${runId}-${stageId}-${Date.now()}`,
        actor: "control-tower",
      });
      setSeal(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The seal request could not be submitted.");
    } finally { setWorking(false); }
  }

  async function handleG12Approve() {
    setWorking(true); setError(null);
    try {
      const result = await submitG12Decision(runId, stageId, {
        expected_state_version: stateVersion,
        idempotency_key: `g12-${runId}-${stageId}-${Date.now()}`,
        actor: "control-tower",
        g12_decision: "APPROVED",
      });
      setSeal(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The G12 approval could not be submitted.");
    } finally { setWorking(false); }
  }

  async function handleG12Reject() {
    setWorking(true); setError(null);
    try {
      const result = await submitG12Decision(runId, stageId, {
        expected_state_version: stateVersion,
        idempotency_key: `g12-${runId}-${stageId}-${Date.now()}`,
        actor: "control-tower",
        g12_decision: "REJECTED",
      });
      setSeal(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The G12 rejection could not be submitted.");
    } finally { setWorking(false); }
  }

  async function handleCopyForward() {
    setWorking(true); setError(null);
    try {
      const result = await startCopyForward(runId, stageId);
      setSeal(result);
    } catch { setError("Copy-forward could not be started."); }
    finally { setWorking(false); }
  }

  const connectionLabel = useMemo(() => (
    connectionStatus === "open" ? "Live seal state"
    : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..."
    : connectionStatus === "recovering" ? "Refreshing authoritative seal state..."
    : connectionStatus === "failed" ? "Unable to refresh seal state"
    : "Connecting to seal events..."
  ), [connectionStatus]);

  const allChecksPassed = seal?.completeness.checks.every((c) => c.status === "passed") ?? false;

  return (
    <section className={styles.panel} aria-labelledby="stage-seal-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F14</p>
          <h2 id="stage-seal-title">Stage seal &amp; copy-forward — G12</h2>
          <p className={styles.note}>
            Verify completeness checks, review output fingerprint, and seal the stage.
          </p>
        </div>
        <span className={styles.status}>{seal ? statusLabel(seal.status) : "not loaded"}</span>
      </div>
      <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>

      {loading && <p role="status">Loading seal state...</p>}
      {error && <p role="alert">{error}</p>}
      {stale && <p role="alert">The run state changed while seal was loading. Refresh before retrying.</p>}

      {!loading && !seal && (
        <p className={styles.note}>No seal has been started yet.</p>
      )}

      {seal && (
        <>
          {/* Completeness checks */}
          <div className={styles.previewPanel}>
            <div className={styles.previewHeader}>
              <h3>Completeness checks</h3>
              {seal.status !== "sealed" && seal.status !== "failed" && seal.status !== "rolled_back" ? (
                <button type="button" onClick={handleSeal} disabled={working}>
                  {working ? "Processing..." : "Run completeness check"}
                </button>
              ) : null}
            </div>
            <ul className={styles.list}>
              {seal.completeness.checks.map((check) => (
                <li key={check.check_id}>
                  <span>{checkEmojis[check.status] ?? "?"}</span>
                  <strong>{check.name}</strong>
                  <strong>{statusLabel(check.status)}</strong>
                  {check.detail && <small>{check.detail}</small>}
                </li>
              ))}
            </ul>
            <p className={styles.note}>Completeness: {statusLabel(seal.completeness.status)}</p>
          </div>

          {/* Output fingerprint */}
          {seal.fingerprint && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h3>Output fingerprint</h3></div>
              <ul className={styles.list}>
                <li><strong>Fingerprint:</strong> <code>{seal.fingerprint.fingerprint}</code></li>
                <li><strong>Algorithm:</strong> {seal.fingerprint.algorithm}</li>
                <li><strong>Assets:</strong> {seal.fingerprint.asset_count}</li>
                <li><strong>Total size:</strong> {seal.fingerprint.total_size_bytes} bytes</li>
                <li><strong>Created at:</strong> {seal.fingerprint.created_at}</li>
              </ul>
            </div>
          )}

          {/* G12 controls */}
          {seal.status !== "sealed" && !seal.g12_decision && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h3>G12 approval</h3></div>
              <p className={styles.note}>
                {allChecksPassed
                  ? "All completeness checks pass. You may approve or reject this stage."
                  : "Some checks did not pass. Review before approving."}
              </p>
              <div className={styles.buttonRow ?? ""}>
                <button type="button" onClick={handleG12Approve} disabled={working}>
                  {working ? "Processing..." : "Approve (G12)"}
                </button>
                <button type="button" onClick={handleG12Reject} disabled={working}>
                  {working ? "Processing..." : "Reject"}
                </button>
              </div>
            </div>
          )}
          {seal.g12_decision && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h3>G12 decision</h3></div>
              <p className={styles.note}>Decision: {statusLabel(seal.g12_decision)}</p>
            </div>
          )}

          {/* Copy-forward status */}
          {seal.copy_forward && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}>
                <h3>Copy-forward</h3>
                {seal.status === "sealed" && seal.copy_forward.status !== "completed" && seal.copy_forward.status !== "failed" && (
                  <button type="button" onClick={handleCopyForward} disabled={working}>
                    {working ? "Starting..." : "Copy forward"}
                  </button>
                )}
              </div>
              <ul className={styles.list}>
                <li><strong>Status:</strong> {statusLabel(seal.copy_forward.status)}</li>
                {seal.copy_forward.source_stage_id && <li><strong>From stage:</strong> {seal.copy_forward.source_stage_id}</li>}
                {seal.copy_forward.target_stage_id && <li><strong>To stage:</strong> {seal.copy_forward.target_stage_id}</li>}
                {seal.copy_forward.copied_artifact_count != null && <li><strong>Artifacts copied:</strong> {seal.copy_forward.copied_artifact_count}</li>}
                {seal.copy_forward.detail && <li><small>{seal.copy_forward.detail}</small></li>}
              </ul>
            </div>
          )}

          <p className={styles.note}>
            state version {seal.state_version} · event sequence {seal.event_sequence}
            {seal.idempotent_replay ? " · idempotent replay" : ""}
          </p>
        </>
      )}
    </section>
  );
}
