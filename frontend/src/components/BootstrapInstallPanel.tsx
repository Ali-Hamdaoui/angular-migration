"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError, getBackendBaseUrl } from "@/api/client";
import { getBootstrapInstallStatus, runBootstrapInstall } from "@/api/stages";
import type { StageBootstrapInstallResponse, StageBootstrapStatusResponse } from "@/api/stages";
import styles from "./BootstrapInstallPanel.module.css";

const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED", "BLOCKED", "STALE", "RECOVERY_REQUIRED"]);
const RUNNING_STATES = new Set(["RUNNING", "in_progress", "QUEUED", "STARTING"]);
const POLL_INTERVAL_MS = 3000;

function formattedDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainSec = seconds % 60;
  return `${minutes}m ${remainSec}s`;
}

export function BootstrapInstallPanel({
  runId,
  stageId,
  runStateVersion,
}: {
  runId: string;
  stageId: string;
  runStateVersion?: number;
}) {
  const [step, setStep] = useState<StageBootstrapStatusResponse | null>(null);
  const [installation, setInstallation] = useState<StageBootstrapInstallResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const result = await getBootstrapInstallStatus(runId, stageId);
      setStep(result);
      return result;
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setStep(null);
        return null;
      }
      throw reason;
    }
  }, [runId, stageId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await fetchStatus();
    } catch {
      setError("Bootstrap install status could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [fetchStatus]);

  useEffect(() => { void refresh(); }, [refresh]);

  // Poll for status updates while running
  useEffect(() => {
    if (!step || TERMINAL.has(step.status)) return;
    const timer = window.setInterval(() => {
      void fetchStatus().catch(() => undefined);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [step, fetchStatus]);

  async function handleStart() {
    setWorking(true);
    setError(null);
    setStale(false);
    try {
      const stableKey = `bootstrap-install-${runId}-${stageId}`;
      const result = await runBootstrapInstall(runId, stageId, {
        expected_state_version: step?.state_version ?? installation?.state_version ?? runStateVersion ?? 1,
        idempotency_key: stableKey,
        actor: "control-tower",
      });
      setInstallation(result);
      setStep(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) {
        const body = reason.responseBody ? JSON.parse(reason.responseBody) : null;
        const code = body?.detail?.error_code;
        if (code === "STALE_STATE_VERSION") setStale(true);
        else setError(`Bootstrap installation blocked: ${body?.detail?.message ?? reason.message}`);
      } else {
        setError("Bootstrap installation could not be started.");
      }
    } finally {
      setWorking(false);
    }
  }

  const status = step?.status ?? "not_started";
  const isRunning = RUNNING_STATES.has(status);
  const isComplete = status === "COMPLETED" || status === "SUCCEEDED" || status === "PASSED";
  const isFailed = status === "FAILED" || status === "CANCELLED" || status === "INTERRUPTED";
  const isCancelled = status === "CANCELLED";
  const isInterrupted = status === "INTERRUPTED";
  const isRecoveryRequired = status === "RECOVERY_REQUIRED" || step?.recovery_required === true;
  const isBlocked = status === "BLOCKED" || status === "blocked";
  const isTerminal = TERMINAL.has(status);

  const logUrl = useMemo(() => {
    if (!step?.artifact_ids?.length) return null;
    const logArtifact = `${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(step.artifact_ids[0])}`;
    return logArtifact;
  }, [step]);

  return (
    <section className={styles.panel} aria-labelledby="bootstrap-install-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F06</p>
          <h2 id="bootstrap-install-title">Bootstrap installation</h2>
          <p className={styles.note}>
            Run the approved bootstrap command in the stage sandbox to set up the working environment.
          </p>
        </div>
        <span className={`${styles.status} ${
          isComplete ? styles.statusSuccess :
          isFailed ? styles.statusFailure :
          isCancelled ? styles.statusFailure :
          isInterrupted ? styles.statusBlocked :
          isRecoveryRequired ? styles.statusBlocked :
          isRunning ? styles.statusRunning :
          isBlocked ? styles.statusBlocked :
          ""
        }`} role="status" aria-live="polite">
          {status.replaceAll("_", " ").toLowerCase()}
        </span>
      </div>

      {loading ? <p role="status" className={styles.statusMessage}>Loading bootstrap install status…</p> : null}

      {error ? <p role="alert" className={styles.errorMessage}>{error}</p> : null}

      {stale ? (
        <p role="alert" className={styles.warningMessage}>
          The stage state changed while processing. Refresh the authoritative state before retrying.
        </p>
      ) : null}

      {/* Empty state */}
      {!loading && !step && !error ? (
        <div className={styles.emptyState}>
          <p className={styles.note}>No bootstrap installation has been started for this stage.</p>
        </div>
      ) : null}

      {/* Approved command */}
      {step?.command ? (
        <div className={styles.commandBlock}>
          <h3>Approved command</h3>
          <pre className={styles.commandPreview}><code>{step.command}</code></pre>
        </div>
      ) : null}

      {/* Progress / log link */}
      {isRunning && logUrl ? (
        <p className={styles.logLink}>
          <a href={logUrl} target="_blank" rel="noreferrer">View live installation logs →</a>
        </p>
      ) : null}

      {isRunning && !logUrl ? (
        <p className={styles.logLink}>Installation in progress. Logs will be available once the command produces output.</p>
      ) : null}

      {/* Result (exit code, duration) */}
      {step && isTerminal ? (
        <div className={styles.resultBlock}>
          <h3>Result</h3>
          <dl className={styles.metadataGrid}>
            <div>
              <dt>Exit code</dt>
              <dd>
                {step.exit_code !== null && step.exit_code !== undefined ? (
                  <span className={step.exit_code === 0 ? styles.exitOk : styles.exitFail}>
                    {step.exit_code}
                  </span>
                ) : "—"}
              </dd>
            </div>
            <div>
              <dt>Started</dt>
              <dd>{step.started_at ? new Date(step.started_at).toLocaleString() : "—"}</dd>
            </div>
            <div>
              <dt>Completed</dt>
              <dd>{step.completed_at ? new Date(step.completed_at).toLocaleString() : "—"}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>
                {step.started_at && step.completed_at
                  ? formattedDuration(
                      Date.parse(step.completed_at) - Date.parse(step.started_at),
                    )
                  : "—"}
              </dd>
            </div>
          </dl>
        </div>
      ) : null}

      {/* In progress metadata */}
      {isRunning && step ? (
        <div className={styles.progressBlock}>
          <h3>Installation progress</h3>
          <dl className={styles.metadataGrid}>
            <div><dt>Started</dt><dd>{step.started_at ? new Date(step.started_at).toLocaleString() : "pending"}</dd></div>
            <div><dt>Step ID</dt><dd><code>{step.step_id}</code></dd></div>
          </dl>
          <div className={styles.progressIndicator}>
            <div className={styles.progressBar}>
              <div className={styles.progressFill} />
            </div>
            <span className={styles.progressLabel}>Running…</span>
          </div>
        </div>
      ) : null}

      {/* Environment blockers */}
      {isBlocked && step ? (
        <div className={styles.blockersBlock}>
          <h3>Environment blockers</h3>
          <p role="alert" className={styles.warningMessage}>
            Bootstrap installation is blocked by the environment. Resolve the following issues before retrying.
          </p>
          {step.artifact_ids.length > 0 ? (
            <ul className={styles.blockerList}>
              {step.artifact_ids.map((id) => (
                <li key={id}>
                  <a
                    className={styles.artifactLink}
                    href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(id)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Artifact {id}
                  </a>
                  — review for environment diagnostics
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.note}>No diagnostic artifacts available. Check the environment inventory for blockers.</p>
          )}
        </div>
      ) : null}

      {/* Failure state with retry guidance */}
      {isFailed && step && step.retry_eligible && !step.recovery_required ? (
        <div className={styles.failureBlock}>
          <h3>Installation failed</h3>
          <p role="alert" className={styles.errorMessage}>
            Exit code: {step.exit_code ?? "unknown"}. The bootstrap command did not complete successfully.
          </p>
          {logUrl ? (
            <p className={styles.retryGuidance}>
              <a href={logUrl} target="_blank" rel="noreferrer">View full logs</a> for detailed error information.
            </p>
          ) : null}
          <div className={styles.retryGuidance}>
            <h4>Retry guidance</h4>
            <ul className={styles.guidanceList}>
              <li>Check the command output logs for specific failure reasons.</li>
              <li>Verify that the stage sandbox has all required dependencies.</li>
              <li>If the environment is misconfigured, request a sandbox reconstruction.</li>
              <li>After resolving the issue, click <strong>Retry bootstrap install</strong> below.</li>
            </ul>
          </div>
        </div>
      ) : null}

      {isFailed && step && !step.retry_eligible && !step.recovery_required ? (
        <div className={styles.failureBlock}>
          <h3>Installation failed</h3>
          <p role="alert" className={styles.errorMessage}>
            {step.failure_classification ?? "The bootstrap command failed."} Retry is not authorized for this workspace state.
          </p>
          {logUrl ? <p><a href={logUrl} target="_blank" rel="noreferrer">View full logs</a></p> : null}
        </div>
      ) : null}

      {/* Artifact links for completed install */}
      {isComplete && step?.artifact_ids?.length ? (
        <div className={styles.artifactSection}>
          <h3>Installation artifacts</h3>
          <ul className={styles.artifactList}>
            {step.artifact_ids.map((id) => (
              <li key={id}>
                <a
                  className={styles.artifactLink}
                  href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(id)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Artifact {id}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {step ? (
        <div className={styles.resultBlock}>
          <h3>Authority and recovery</h3>
          <dl className={styles.metadataGrid}>
            <div><dt>Runtime profile</dt><dd>{step.runtime_profile ?? "—"}</dd></div>
            <div><dt>Stage sandbox</dt><dd>{step.stage_sandbox ?? "—"}</dd></div>
            <div><dt>G07</dt>
              <dd className={step.g07_status === "approved" || step.g07_status === "approved_with_comment" ? styles.exitOk : styles.exitFail}>
                {step.g07_status ?? "—"}
              </dd>
            </div>
            <div><dt>Lifecycle audit</dt><dd>{step.lifecycle_script_audit_ref ?? "—"}</dd></div>
            <div><dt>Pre-fingerprint</dt><dd><code>{step.pre_fingerprint ?? "—"}</code></dd></div>
            <div><dt>Post-fingerprint</dt><dd><code>{step.post_fingerprint ?? "—"}</code></dd></div>
            <div><dt>Correlation ID</dt><dd><code>{step.correlation_id ?? "—"}</code></dd></div>
            <div><dt>Failure classification</dt><dd className={step.failure_classification ? styles.exitFail : ""}>{step.failure_classification ?? "—"}</dd></div>
          </dl>
          {step.recovery_required || isRecoveryRequired ? (
            <p role="alert" className={styles.warningMessage}>
              {step.reconstruction_guidance ?? "The stage sandbox must be reconstructed before another install."}
            </p>
          ) : null}
          {step.g07_status === "missing" ? (
            <p role="alert" className={styles.errorMessage}>
              G07 authorization record is missing. Bootstrap must have an approved G07 gate to proceed.
            </p>
          ) : null}
          {step.g07_status && step.g07_status !== "approved" && step.g07_status !== "approved_with_comment" && step.g07_status !== "missing" ? (
            <p role="alert" className={styles.warningMessage}>
              G07 status is "{step.g07_status}". Bootstrap authorization may be revoked or stale.
            </p>
          ) : null}
        </div>
      ) : null}

      {/* Action buttons */}
      <div className={styles.actions}>
        <span>Step: {step?.step_id ?? "—"}</span>
        <div className={styles.actionButtons}>
          {(status === "not_started" || step?.retry_eligible) && !isRunning ? (
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryButton}`}
              disabled={working || isRunning}
              onClick={handleStart}
            >
              {working
                ? "Starting…"
                : step?.retry_eligible
                  ? "Retry bootstrap install"
                  : "Start bootstrap install"}
            </button>
          ) : null}
          {isComplete ? (
            <span className={styles.completeNotice}>Bootstrap installation completed successfully.</span>
          ) : null}
          {isRunning ? (
            <span className={styles.runningNotice}>Installation in progress. Status updates every {POLL_INTERVAL_MS / 1000}s.</span>
          ) : null}
        </div>
      </div>
    </section>
  );
}
