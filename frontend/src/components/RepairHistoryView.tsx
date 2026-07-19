"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getRepairChain,
  recoverRepairChain,
} from "../api/patches";
import type {
  AttemptRecord,
  DiagnosticHold,
  RepairChainResult,
} from "../api/patches";
import styles from "./RepairHistoryView.module.css";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface RepairHistoryViewProps {
  runId: string;
  chainId: string;
}

type ViewState =
  | "loading"
  | "empty"
  | "running"
  | "success"
  | "blocked"
  | "stale"
  | "reconnecting"
  | "backend-failure";

type RecoveryActionKind = "rollback" | "reconstruct" | "unknown";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const POLL_INTERVAL_MS = 10_000;
const STALE_THRESHOLD_MS = 60_000;
const RECONNECT_DELAY_MS = 3_000;
const MAX_RECONNECT_ATTEMPTS = 3;

const NO_PROGRESS_INDICATORS: Record<string, string> = {
  duplicate_patch: "Duplicate patch detected — identical diff content as a prior attempt",
  identical_fingerprint: "Identical workspace fingerprint — no changes since last attempt",
  no_error_delta: "No error delta — error set unchanged from previous attempt",
  attempt_limit: "Attempt limit reached — maximum repair attempts exhausted",
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Determine the view state from the chain result and staleness flag. */
function deriveViewState(
  chain: RepairChainResult | null,
  isStale: boolean,
): ViewState {
  if (!chain) return "empty";

  if (isStale) return "stale";

  switch (chain.status) {
    case "in_progress":
    case "running":
    case "pending":
      return "running";
    case "completed":
    case "success":
      return "success";
    case "blocked":
    case "diagnostic_hold":
    case "failed":
    case "error":
      return "blocked";
    default:
      return "empty";
  }
}

/** Map an attempt outcome to a CSS class name. */
function outcomeClass(outcome: string): string {
  switch (outcome) {
    case "applied":
    case "success":
    case "passed":
      return styles.outcomeSuccess;
    case "failed":
    case "rejected":
    case "error":
      return styles.outcomeFailure;
    case "skipped":
    case "cancelled":
      return styles.outcomeSkipped;
    case "in_progress":
    case "running":
      return styles.outcomeRunning;
    default:
      return styles.outcomeUnknown;
  }
}

/** Human-readable outcome label. */
function outcomeLabel(outcome: string): string {
  return outcome.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Is the chain in a state that should auto-poll? */
function shouldPoll(status: string): boolean {
  return ["in_progress", "running", "pending"].includes(status);
}

/** Parse a recovery_action from the chain into a typed kind. */
function recoveryActionKind(action: string | null): RecoveryActionKind | null {
  if (!action) return null;
  const lower = action.toLowerCase();
  if (lower.includes("rollback")) return "rollback";
  if (lower.includes("reconstruct")) return "reconstruct";
  return "unknown";
}

/** Extract no-progress indicator descriptions from the reason string. */
function parseNoProgressIndicators(reason: string | null): string[] {
  if (!reason) return [];
  const indicators: string[] = [];
  const lower = reason.toLowerCase();

  for (const [key, description] of Object.entries(NO_PROGRESS_INDICATORS)) {
    if (lower.includes(key)) {
      indicators.push(description);
    }
  }

  // If the reason contains text that doesn't match known indicators,
  // show the raw reason as a fallback.
  if (indicators.length === 0) {
    indicators.push(reason);
  }

  return indicators;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function RepairHistoryView({ runId, chainId }: RepairHistoryViewProps) {
  /* ---- State ---- */
  const [chain, setChain] = useState<RepairChainResult | null>(null);
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [recovering, setRecovering] = useState(false);
  const [recoveryResult, setRecoveryResult] = useState<string | null>(null);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  /* ---- Refs ---- */
  const lastUpdateRef = useRef<number>(Date.now());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const staleCheckRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  /* ---- Data fetching ---- */

  const loadChain = useCallback(async () => {
    try {
      const result = await getRepairChain(runId, chainId);
      if (!mountedRef.current) return;

      setChain(result);
      lastUpdateRef.current = Date.now();
      setErrorMessage(null);
      setReconnectAttempts(0);

      // Determine new view state (stale detection is separate)
      const newState = deriveViewState(result, false);
      setViewState(newState);
    } catch (err: unknown) {
      if (!mountedRef.current) return;

      const message =
        err instanceof Error ? err.message : "Failed to load repair chain";

      // If we already have data and the fetch fails, try reconnecting
      if (chain) {
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          setViewState("reconnecting");
          setErrorMessage(message);
        } else {
          setViewState("backend-failure");
          setErrorMessage("Backend unreachable after multiple retries. " + message);
        }
      } else {
        // No data yet — initial load failure
        setErrorMessage(message);
        setViewState("backend-failure");
      }
    }
  }, [runId, chainId, chain, reconnectAttempts]);

  /* ---- Initial load ---- */

  useEffect(() => {
    mountedRef.current = true;
    void loadChain();

    return () => {
      mountedRef.current = false;
    };
  }, [loadChain]);

  /* ---- Polling when running ---- */

  useEffect(() => {
    if (shouldPoll(chain?.status ?? "")) {
      pollRef.current = setInterval(() => {
        void loadChain();
      }, POLL_INTERVAL_MS);
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [chain?.status, loadChain]);

  /* ---- Staleness detection ---- */

  useEffect(() => {
    staleCheckRef.current = setInterval(() => {
      if (!mountedRef.current) return;
      if (!chain) return;

      const elapsed = Date.now() - lastUpdateRef.current;
      if (elapsed > STALE_THRESHOLD_MS && viewState !== "stale") {
        setViewState("stale");
      }
    }, 15_000);

    return () => {
      if (staleCheckRef.current) {
        clearInterval(staleCheckRef.current);
        staleCheckRef.current = null;
      }
    };
  }, [chain, viewState]);

  /* ---- Reconnect timer ---- */

  useEffect(() => {
    if (viewState === "reconnecting") {
      reconnectRef.current = setTimeout(() => {
        if (mountedRef.current) {
          setReconnectAttempts((n: number) => n + 1);
          void loadChain();
        }
      }, RECONNECT_DELAY_MS);
    }

    return () => {
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
    };
  }, [viewState, loadChain]);

  /* ---- Recovery action ---- */

  async function handleRecover(action: string) {
    setRecovering(true);
    setRecoveryResult(null);
    setRecoveryError(null);

    try {
      const result = await recoverRepairChain(runId, chainId, {
        chain_id: chainId,
        run_id: runId,
        stage_id: action === "rollback" ? "ROLLBACK" : "RECONSTRUCT",
        idempotency_key: `repair-recover-${chainId}-${Date.now()}`,
        actor: "control-tower",
      });

      if (!mountedRef.current) return;

      setRecoveryResult(`${action} initiated — ${result.status}`);
      // Refresh the chain after recovery
      void loadChain();
    } catch (err: unknown) {
      if (!mountedRef.current) return;

      const message =
        err instanceof Error
          ? err.message
          : `${action} request failed`;
      setRecoveryError(message);
    } finally {
      if (mountedRef.current) {
        setRecovering(false);
      }
    }
  }

  /* ---- Manual refresh ---- */

  async function handleRefresh() {
    setReconnectAttempts(0);
    setErrorMessage(null);
    await loadChain();
  }

  /* ---- Derived values ---- */

  const noProgressIndicators = chain
    ? parseNoProgressIndicators(chain.no_progress_reason)
    : [];
  const hasHold = chain?.diagnostic_hold != null;
  const recAction =
    chain && chain.recovery_action
      ? recoveryActionKind(chain.recovery_action)
      : null;
  const hasArtifacts =
    chain &&
    chain.artifact_refs &&
    Object.keys(chain.artifact_refs).length > 0;
  const isEmpty =
    viewState === "empty" || (chain && chain.total_attempts === 0);

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <section className={styles.panel} aria-label="Repair history">
      {/* ---- Header ---- */}
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>S4-F09 · Repair chain</p>
          <h2 className={styles.title}>Repair History</h2>
          <p className={styles.chainMeta}>
            Chain <strong>{chainId}</strong> · Run <strong>{runId}</strong>
            {chain ? (
              <>
                {" · "}
                {chain.total_attempts} attempt{chain.total_attempts !== 1 ? "s" : ""}
                {chain.duplicate_count > 0
                  ? ` (${chain.duplicate_count} duplicate${chain.duplicate_count !== 1 ? "s" : ""})`
                  : ""}
              </>
            ) : null}
          </p>
        </div>

        {viewState !== "loading" && (
          <button
            className={styles.refreshBtn}
            type="button"
            onClick={handleRefresh}
            disabled={viewState === "reconnecting"}
          >
            Refresh
          </button>
        )}
      </div>

      {/* ---- Loading state ---- */}
      {viewState === "loading" && (
        <div className={styles.loadingState}>
          <span className={styles.spinner} />
          Loading repair chain…
        </div>
      )}

      {/* ---- Backend-failure (no data) ---- */}
      {viewState === "backend-failure" && !chain && (
        <>
          <div className={styles.statusEmpty}>
            <span>No chain data</span>
          </div>
          <div className={styles.errorBanner}>
            {errorMessage ?? "Repair chain could not be loaded."}
          </div>
        </>
      )}

      {/* ---- Empty state ---- */}
      {isEmpty && chain && (
        <div className={styles.emptyState}>
          No repair attempts recorded for this chain. Awaiting first patch
          attempt.
        </div>
      )}

      {/* ---- Stale banner ---- */}
      {viewState === "stale" && chain && (
        <div className={styles.statusStale}>
          <span>⚠ Stale data — chain state may have advanced</span>
          <button
            className={styles.refreshSmall}
            type="button"
            onClick={handleRefresh}
          >
            Refresh
          </button>
        </div>
      )}

      {/* ---- Running banner ---- */}
      {viewState === "running" && (
        <div className={styles.statusRunning}>
          <span className={styles.spinner} />
          Repair in progress…
        </div>
      )}

      {/* ---- Success banner ---- */}
      {viewState === "success" && (
        <div className={styles.statusSuccess}>
          <span>✓ Repair completed</span>
          {chain && chain.applied_attempts > 0 && (
            <span>
              {chain.applied_attempts} of {chain.total_attempts} applied
            </span>
          )}
        </div>
      )}

      {/* ---- Blocked banner ---- */}
      {viewState === "blocked" && (
        <div className={styles.statusBlocked}>
          <span>⛔ Blocked</span>
          {chain?.no_progress_reason && (
            <span>{chain.no_progress_reason}</span>
          )}
        </div>
      )}

      {/* ---- Reconnecting banner ---- */}
      {viewState === "reconnecting" && (
        <div className={styles.reconnectBanner}>
          <span className={styles.spinner} />
          Connection lost — retrying ({reconnectAttempts + 1}/
          {MAX_RECONNECT_ATTEMPTS})…
        </div>
      )}

      {/* ---- Backend-failure (had data, then lost it) ---- */}
      {viewState === "backend-failure" && chain && (
        <div className={styles.errorBanner}>
          ⚠ {errorMessage ?? "Backend error"}
          <button
            className={styles.refreshSmall}
            type="button"
            onClick={handleRefresh}
          >
            Retry
          </button>
        </div>
      )}

      {/* ---- Attempt table ---- */}
      {chain && chain.attempts.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Attempts</h3>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Attempt ID</th>
                  <th>Outcome</th>
                  <th>Fingerprint</th>
                </tr>
              </thead>
              <tbody>
                {chain.attempts.map((attempt: AttemptRecord) => (
                  <tr key={attempt.attempt_id}>
                    <td className={styles.attemptNum}>
                      {attempt.attempt_number}
                    </td>
                    <td className={styles.fingerprint}>
                      {attempt.attempt_id}
                    </td>
                    <td>
                      <span className={outcomeClass(attempt.outcome)}>
                        {outcomeLabel(attempt.outcome)}
                      </span>
                    </td>
                    <td>
                      <span
                        className={
                          attempt.attempt_id
                            ? styles.fingerprint
                            : styles.emptyFingerprint
                        }
                        title="Unique workspace fingerprint for this attempt"
                      >
                        {attempt.attempt_id
                          ? attempt.attempt_id.slice(0, 16) + "…"
                          : "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---- No-progress detection ---- */}
      {chain && noProgressIndicators.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>No-Progress Detection</h3>
          <div className={styles.noProgressBlock}>
            {chain.no_progress_reason &&
              !Object.keys(NO_PROGRESS_INDICATORS).some((k) =>
                chain.no_progress_reason!.toLowerCase().includes(k),
              ) && (
                <p className={styles.noProgressReason}>
                  {chain.no_progress_reason}
                </p>
              )}

            <ul className={styles.noProgressList}>
              {noProgressIndicators.map((indicator, i) => (
                <li key={i}>{indicator}</li>
              ))}
            </ul>

            {chain.duplicate_count > 0 && (
              <p className={styles.noProgressDetail}>
                Duplicate patches: {chain.duplicate_count} of{" "}
                {chain.total_attempts} attempts
              </p>
            )}

            {chain.no_progress_reason &&
              chain.no_progress_reason.toLowerCase().includes("limit") && (
                <p className={styles.noProgressDetail}>
                  Attempt limit reached — no further auto-retries will be
                  attempted.
                </p>
              )}
          </div>
        </div>
      )}

      {/* ---- Diagnostic hold ---- */}
      {hasHold && chain?.diagnostic_hold && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Diagnostic Hold</h3>
          <div className={styles.holdBanner}>
            <p className={styles.holdTitle}>⛔ Repair held for diagnosis</p>
            <p className={styles.holdReason}>
              {chain.diagnostic_hold.reason}
            </p>
            <ul className={styles.holdStats}>
              <li>Attempts before hold: {chain.diagnostic_hold.attempt_count}</li>
              <li>
                Duplicates before hold: {chain.diagnostic_hold.duplicate_count}
              </li>
              {chain.diagnostic_hold.held_at && (
                <li>
                  Held at:{" "}
                  {new Date(
                    chain.diagnostic_hold.held_at,
                  ).toLocaleString()}
                </li>
              )}
            </ul>
          </div>
        </div>
      )}

      {/* ---- Recovery actions ---- */}
      {recAction && chain?.recovery_action && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Recovery</h3>
          <p className={styles.note}>
            Recommended action:{" "}
            <strong className={styles.warning}>
              {chain.recovery_action}
            </strong>
          </p>
          <div className={styles.recoveryActions}>
            {(recAction === "rollback" || recAction === "unknown") && (
              <button
                className={styles.recoveryRollback}
                type="button"
                disabled={recovering}
                onClick={() => handleRecover("rollback")}
              >
                {recovering ? "Submitting…" : "Rollback"}
              </button>
            )}
            {(recAction === "reconstruct" || recAction === "unknown") && (
              <button
                className={styles.recoveryReconstruct}
                type="button"
                disabled={recovering}
                onClick={() => handleRecover("reconstruct")}
              >
                {recovering ? "Submitting…" : "Reconstruct"}
              </button>
            )}
          </div>

          {recoveryResult && (
            <div className={styles.recoveryOk}>{recoveryResult}</div>
          )}
          {recoveryError && (
            <div className={styles.recoveryError}>{recoveryError}</div>
          )}
        </div>
      )}

      {/* ---- Artifact links ---- */}
      {hasArtifacts && chain && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Artifacts</h3>
          <div className={styles.artifactLinks}>
            {Object.entries(chain.artifact_refs).map(([name, ref]) => (
              <a
                key={name}
                className={styles.artifactLink}
                href={ref}
                target="_blank"
                rel="noopener noreferrer"
                title={name}
              >
                {name}
              </a>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
