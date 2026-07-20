"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { getAngularUpdate, getTargetVersionTyped, startAngularUpdate, verifyTargetVersion } from "@/api/transformations";
import type { AngularUpdateResponse, TargetVersionResponse } from "@/types/transformation";
import type { WorkflowEventDto } from "@/types/generated/api";
import { StatusPill } from "@/components/StatusPill";
import { LogViewer } from "@/components/LogViewer";
import styles from "./ControlTowerShell.module.css";

type ViewState = "loading" | "empty" | "running" | "success" | "blocked" | "stale" | "reconnecting" | "failure" | "cancelled" | "no_evidence";

interface Props {
  runId: string;
  stageId: string;
  sourceVersion: string;
  targetVersion: string;
  expectedStateVersion: number;
  onStateChange?: (newVersion: number) => void;
  workflowEvents?: WorkflowEventDto[];
}

export function AngularUpdatePanel({
  runId,
  stageId,
  sourceVersion,
  targetVersion,
  expectedStateVersion,
  onStateChange,
  workflowEvents = [],
}: Props) {
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [updateResult, setUpdateResult] = useState<AngularUpdateResponse | null>(null);
  const [targetVersionResult, setTargetVersionResult] = useState<TargetVersionResponse | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittedRef = useRef(false);
  const idempotencyRef = useRef<string | null>(null);

  const addLog = useCallback((msg: string) => {
    setLogs((prev) => [...prev, `[${new Date().toISOString()}] ${msg}`]);
  }, []);

  const handleStateChange = useCallback((result: AngularUpdateResponse) => {
    if (result.target_version_status === "verified") {
      setViewState("success");
    } else if (result.status === "succeeded" && result.target_version_status !== "mismatch" && result.target_version_status !== "inconclusive") {
      setViewState("success");
    } else if (result.status === "failed" || result.target_version_status === "failed" || result.target_version_status === "mismatch") {
      setViewState("failure");
      setError(result.error_message ?? (result.target_version_status === "mismatch" ? "Target version mismatch" : "Angular update failed"));
    } else if (result.status === "interactive_blocked") {
      setViewState("blocked");
    } else if (result.status === "running") {
      setViewState("running");
    } else {
      setViewState("empty");
    }
    setUpdateResult(result);
  }, []);

  const fetchState = useCallback(async () => {
    try {
      setViewState("reconnecting");
      const result = await getAngularUpdate(runId, stageId);
      if (!result) {
        setViewState("no_evidence");
        return;
      }
      handleStateChange(result);
    } catch {
      setViewState("no_evidence");
    }
  }, [runId, stageId, handleStateChange]);

  useEffect(() => {
    fetchState();
  }, [fetchState]);

  useEffect(() => {
    for (const event of workflowEvents) {
      if (event.event_type === "ANGULAR_UPDATE_COMPLETED") {
        const payload = event.payload as Record<string, unknown>;
        if (payload.target_version_status === "verified") {
          setViewState("success");
          addLog("Angular update completed (SSE)");
          if (typeof payload.state_version === "number") {
            onStateChange?.(payload.state_version);
          }
        } else if (payload.target_version_status === "mismatch" || payload.target_version_status === "inconclusive") {
          setViewState("failure");
          setError(payload.target_version_status === "mismatch" ? "Target version mismatch" : "Target version inconclusive");
          addLog(`Angular update completed but target version ${payload.target_version_status} (SSE)`);
        } else {
          setViewState("success");
          addLog("Angular update completed (SSE)");
        }
      } else if (event.event_type === "ANGULAR_UPDATE_FAILED") {
        setViewState("failure");
        const payload = event.payload as Record<string, unknown>;
        const isCancellation = payload.error_message && typeof payload.error_message === "string" && payload.error_message.toLowerCase().includes("cancell");
        if (isCancellation) {
          setViewState("cancelled");
          setError("Angular update was cancelled");
          addLog("Angular update cancelled (SSE)");
        } else {
          setError(typeof payload.error_message === "string" ? payload.error_message : "Angular update failed");
          addLog("Angular update failed (SSE)");
        }
      } else if (event.event_type === "TARGET_VERSION_FAILED") {
        setViewState("failure");
        setError("Target version verification failed");
        addLog("Target version verification failed (SSE)");
      } else if (event.event_type === "INTERACTIVE_DECISION_REQUIRED") {
        setViewState("blocked");
        addLog("Interactive prompt detected (SSE)");
      }
    }
  }, [workflowEvents, onStateChange, addLog]);

  const handleStartUpdate = async () => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    const idempotencyKey = `ang-upd-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    idempotencyRef.current = idempotencyKey;
    try {
      setViewState("running");
      addLog(`Starting Angular update: ${sourceVersion} → ${targetVersion}`);
      const result = await startAngularUpdate(runId, stageId, {
        expected_state_version: expectedStateVersion,
        idempotency_key: idempotencyKey,
        actor: "operator",
        source_version: sourceVersion,
        target_version: targetVersion,
      });
      setUpdateResult(result);
      handleStateChange(result);
      addLog(result.status === "succeeded" ? "Angular update completed successfully" : `Update status: ${result.status}`);
      onStateChange?.(result.state_version);
    } catch (err: unknown) {
      setViewState("failure");
      const message = err instanceof Error ? err.message : "Failed to start Angular update";
      setError(message);
      addLog(`Error: ${message}`);
    } finally {
      setSubmitting(false);
      setTimeout(() => { submittedRef.current = false; }, 1000);
    }
  };

  const handleVerifyTarget = async () => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    const idempotencyKey = `ang-verify-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      const result = await verifyTargetVersion(runId, stageId, {
        expected_state_version: expectedStateVersion,
        idempotency_key: idempotencyKey,
        actor: "operator",
        command_execution_id: updateResult?.command_execution_id ?? "",
      });
      setUpdateResult(result);
      if (result.target_version_status === "verified") {
        addLog(`Target version verified: ${result.resolved_target_version}`);
        onStateChange?.(result.state_version);
      } else if (result.target_version_status === "mismatch") {
        setViewState("failure");
        setError(`Target version mismatch: expected ${targetVersion}, resolved ${result.resolved_target_version}`);
        addLog("Target version mismatch");
      } else if (result.target_version_status === "failed") {
        setViewState("failure");
        setError("Target version verification failed");
        addLog("Target version verification failed");
      } else {
        addLog(`Version check completed: ${result.target_version_status}`);
      }
      onStateChange?.(result.state_version);
    } catch (err: unknown) {
      addLog(`Version check failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSubmitting(false);
      setTimeout(() => { submittedRef.current = false; }, 1000);
    }
  };

  const handleFetchTargetVersion = useCallback(async () => {
    try {
      const result = await getTargetVersionTyped(runId, stageId);
      setTargetVersionResult(result);
      const sourceCount = Object.keys(result.evidence_sources).length;
      addLog(`Target version: ${result.resolved_target_version} (sources: ${sourceCount})`);
      if (!result.all_sources_agree) {
        setError("Target version sources disagree");
      }
    } catch (err: unknown) {
      addLog(`Target version fetch failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  }, [runId, stageId, addLog]);

  useEffect(() => {
    if (viewState === "success" && !targetVersionResult) {
      handleFetchTargetVersion();
    }
  }, [viewState, targetVersionResult, handleFetchTargetVersion]);

  const isRunning = submitting || viewState === "running";

  if (viewState === "loading") {
    return (
      <section className={styles.panel} aria-labelledby="angular-update-title">
        <div className={styles.header}>
          <div>
            <p className={styles.kicker}>S3-F07 angular transform</p>
            <h2 id="angular-update-title">Angular Update</h2>
          </div>
        </div>
        <div role="status">
          <p className={styles.note}>Loading Angular update state…</p>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.panel} aria-labelledby="angular-update-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F07 angular transform</p>
          <h2 id="angular-update-title">Angular Update</h2>
        </div>
        <StatusPill value={
          viewState === "success" ? "PASSED" :
          viewState === "failure" ? "FAILED" :
          viewState === "cancelled" ? "FAILED" :
          viewState === "blocked" ? "BLOCKED" :
          viewState === "stale" ? "STALE" :
          viewState === "no_evidence" ? "WARNING" :
          "RUNNING"
        } />
      </div>

      <div className={styles.dimensionGrid} aria-label="Version matrix">
        <div>
          <span>Source</span>
          <strong>{sourceVersion}</strong>
        </div>
        <div>
          <span>Target</span>
          <strong>{targetVersion}</strong>
        </div>
        {updateResult?.resolved_target_version && (
          <div>
            <span>Resolved target</span>
            <strong>
              {updateResult.resolved_target_version}
              {updateResult.target_version_status === "verified" && " ✓"}
              {updateResult.target_version_status === "mismatch" && " ✗"}
            </strong>
          </div>
        )}
        {updateResult?.command_execution_id && (
          <div>
            <span>Execution ID</span>
            <strong>{updateResult.command_execution_id}</strong>
          </div>
        )}
        {updateResult?.artifact_ids && updateResult.artifact_ids.length > 0 && (
          <div>
            <span>Artifacts</span>
            <strong>{updateResult.artifact_ids.length}</strong>
          </div>
        )}
      </div>

      {targetVersionResult && (
        <div className={styles.dimensionGrid} aria-label="Target verification matrix">
          <div>
            <span>Sources agree</span>
            <strong>{targetVersionResult.all_sources_agree ? "Yes ✓" : "No ✗"}</strong>
          </div>
          {Object.entries(targetVersionResult.evidence_sources).map(([key, value]) => (
            <div key={key}>
              <span>{key.replace(/_/g, " ")}</span>
              <strong>{value || "—"}</strong>
            </div>
          ))}
          {targetVersionResult.disagreements.length > 0 && (
            <div>
              <span>Disagreements</span>
              <strong>{targetVersionResult.disagreements.length}</strong>
            </div>
          )}
        </div>
      )}

      <div className={styles.row}>
        <span>State version {expectedStateVersion}</span>
        {viewState === "empty" && (
          <button
            type="button"
            onClick={handleStartUpdate}
            disabled={isRunning || !sourceVersion || !targetVersion}
            aria-label="Start Angular Update"
          >
            {submitting ? "Starting…" : "Start Angular Update"}
          </button>
        )}
        {viewState === "success" && (
          <button
            type="button"
            onClick={handleVerifyTarget}
            disabled={submitting || isRunning}
            aria-label="Verify Target Version"
          >
            {submitting ? "Verifying…" : "Verify Target Version"}
          </button>
        )}
      </div>

      {viewState === "failure" && error && (
        <div role="alert" className={styles.note}>
          {error}
        </div>
      )}

      {viewState === "cancelled" && (
        <div role="alert" className={styles.note}>
          {error || "Angular update was cancelled."}
        </div>
      )}

      {viewState === "blocked" && (
        <div role="alert" className={styles.note}>
          Interactive prompt detected. Manual intervention required.
        </div>
      )}

      {viewState === "stale" && (
        <div role="alert" className={styles.note}>
          State version changed. Reloading snapshot…
        </div>
      )}

      {viewState === "no_evidence" && (
        <div role="alert" className={styles.note}>
          No Angular update evidence found for this stage.
        </div>
      )}

      {viewState === "reconnecting" && (
        <div role="status" className={styles.note}>
          Reconnecting…
        </div>
      )}

      {logs.length > 0 && (
        <div aria-live="polite">
          <h3 className={styles.kicker}>Logs</h3>
          <LogViewer content={logs.join("\n")} maxLines={200} />
        </div>
      )}
    </section>
  );
}
