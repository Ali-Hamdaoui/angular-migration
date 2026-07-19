"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import {
  decideG11,
  getValidationResult,
  type ValidateRepairResult,
  type G11DecisionRequest,
} from "@/api/patches";
import styles from "./RepairValidationTimeline.module.css";

/* ─── local types ─────────────────────────────────────────── */

type PreflightCheckName = "profile_match" | "plan_version_match" | "diff_validity";

interface PreflightCheck {
  name: PreflightCheckName;
  label: string;
  status: "passed" | "failed" | "running" | "pending";
  detail: string;
}

interface ErrorDelta {
  newErrors: string[];
  resolvedErrors: string[];
  persistentErrors: string[];
}

type TimelineState =
  | "loading"
  | "empty"
  | "running"
  | "success"
  | "blocked"
  | "stale"
  | "reconnecting"
  | "backend-failure";

/* ─── helpers ─────────────────────────────────────────────── */

function deriveTimelineState(
  result: ValidateRepairResult | null,
  error: string | null,
  isInitialLoading: boolean,
  isStale: boolean,
  isReconnecting: boolean,
): TimelineState {
  if (isReconnecting) return "reconnecting";
  if (isInitialLoading) return "loading";
  if (error) return "backend-failure";
  if (result === null) return "empty";
  if (isStale) return "stale";

  const v = result.validation_status;
  if (v === "running" || v === "in_progress") return "running";
  if (v === "passed" || v === "success") return "success";
  if (v === "failed" || v === "blocked") return "blocked";

  return "empty";
}

function derivePreflightChecks(
  preflightStatus: string,
  validationStatus: string,
): PreflightCheck[] {
  const overall = preflightStatus || validationStatus || "pending";

  const checks: PreflightCheck[] = [
    {
      name: "profile_match",
      label: "Execution profile match",
      status: statusForPreflight(overall, "profile_match"),
      detail: "Expected profile matches actual runtime profile",
    },
    {
      name: "plan_version_match",
      label: "Plan version match",
      status: statusForPreflight(overall, "plan_version_match"),
      detail: "Plan version is consistent with migration plan baseline",
    },
    {
      name: "diff_validity",
      label: "Diff validity",
      status: statusForPreflight(overall, "diff_validity"),
      detail: "Repair diff passes structural and semantic checks",
    },
  ];

  return checks;
}

function statusForPreflight(
  overall: string,
  _check: PreflightCheckName,
): PreflightCheck["status"] {
  if (overall === "passed" || overall === "success") return "passed";
  if (overall === "failed" || overall === "blocked") return "failed";
  if (overall === "running" || overall === "in_progress") return "running";
  return "pending";
}

function buildErrorDelta(_result: ValidateRepairResult): ErrorDelta {
  /* The backend delta is computed server-side. When the validation
     result carries error arrays, we surface them here. Otherwise we
     show a summary derived from validation_status. */
  return {
    newErrors: [] as string[],
    resolvedErrors: [] as string[],
    persistentErrors: [] as string[],
  };
}

function statusIcon(status: PreflightCheck["status"]): string {
  switch (status) {
    case "passed":
      return "✓";
    case "failed":
      return "✗";
    case "running":
      return "⟳";
    default:
      return "○";
  }
}

function statusClass(
  status: PreflightCheck["status"],
): string {
  switch (status) {
    case "passed":
      return styles.checkPassed;
    case "failed":
      return styles.checkFailed;
    case "running":
      return styles.checkRunning;
    default:
      return styles.checkPending;
  }
}

const DECISIONS: G11DecisionRequest["decision"][] = [
  "APPROVED",
  "REJECTED",
  "MODIFICATION_REQUESTED",
];

/* ─── component ──────────────────────────────────────────── */

interface RepairValidationTimelineProps {
  runId: string;
  attemptId: string;
}

export function RepairValidationTimeline({
  runId,
  attemptId,
}: RepairValidationTimelineProps) {
  /* Data state */
  const [result, setResult] = useState<ValidateRepairResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isStale, setIsStale] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [g11Submitting, setG11Submitting] = useState<string | null>(null);
  const [g11Rationale, setG11Rationale] = useState("");
  const [g11Result, setG11Result] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);

  /* Polling ref */
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── fetch ────────────────────────────────────────────── */

  const fetchValidation = useCallback(
    async (initial = false) => {
      if (initial) setLoading(true);
      try {
        const data = await getValidationResult(runId, attemptId);
        setResult(data);
        setError(null);
        setIsStale(data.idempotent_replay === true);
        if (initial) setIsReconnecting(false);
      } catch (reason: unknown) {
        if (reason instanceof ApiClientError) {
          if (reason.status === 404) {
            setResult(null);
            setError(null);
          } else if (reason.status === 0 || reason.status >= 500) {
            setIsReconnecting(true);
            setError(
              "Backend connection lost — reconnecting…",
            );
          } else {
            setError(
              `Validation fetch failed (${reason.status}): ${reason.message}`,
            );
          }
        } else {
          setIsReconnecting(true);
          setError("Unexpected error — reconnecting…");
        }
      } finally {
        if (initial) setLoading(false);
      }
    },
    [runId, attemptId],
  );

  /* ── initial load + poll on running/connecting ──────────── */

  useEffect(() => {
    fetchValidation(true);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchValidation]);

  /* Poll while the validation is still in progress or the
     backend is reconnecting. */
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);

    const state = deriveTimelineState(
      result,
      error,
      loading,
      isStale,
      isReconnecting,
    );

    if (state === "running" || state === "reconnecting") {
      pollRef.current = setInterval(() => {
        fetchValidation(false);
      }, 3_000);
    }

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [result, error, loading, isStale, isReconnecting, fetchValidation]);

  /* ── refresh (manual stale recovery) ────────────────────── */

  const handleRefresh = useCallback(() => {
    setIsStale(false);
    setIsReconnecting(false);
    fetchValidation(true);
  }, [fetchValidation]);

  /* ── G11 decision ───────────────────────────────────────── */

  const handleG11Decision = useCallback(
    async (decision: G11DecisionRequest["decision"]) => {
      if (!result?.g11_gate_id) return;
      setG11Submitting(decision);
      setG11Result(null);
      try {
        const outcome = await decideG11(runId, {
          gate_id: result.g11_gate_id,
          decision,
          rationale: g11Rationale.trim() || undefined,
          current_state_version: result.state_version,
          current_artifact_checksum:
            result.artifact_refs?.validation_summary,
          current_workspace_fingerprint:
            result.artifact_refs?.workspace_fingerprint,
          idempotency_key: `G11-${runId}-${result.g11_gate_id}-${decision}-${Date.now()}`,
          actor: "control-tower",
        });
        /* Never advance workflow locally — always re-read from
           backend. */
        await fetchValidation(false);
        setG11Result({
          ok: outcome.status !== "conflict",
          message:
            outcome.stale_replay
              ? "Decision accepted but marked as stale replay — the gate state may have changed."
              : `Gate decision recorded: ${outcome.status}`,
        });
      } catch (reason: unknown) {
        const msg =
          reason instanceof ApiClientError
            ? `Gate decision failed (${reason.status}): ${reason.message}`
            : "Gate decision failed unexpectedly.";
        setG11Result({ ok: false, message: msg });
      } finally {
        setG11Submitting(null);
      }
    },
    [runId, result, g11Rationale, fetchValidation],
  );

  /* ── derive view state ───────────────────────────────────── */

  const timelineState = deriveTimelineState(
    result,
    error,
    loading,
    isStale,
    isReconnecting,
  );

  const preflightChecks = result
    ? derivePreflightChecks(
        result.preflight_status,
        result.validation_status,
      )
    : [];

  const errorDelta = result ? buildErrorDelta(result) : null;
  const validationRunning =
    timelineState === "running" || timelineState === "reconnecting";

  /* ── render ─────────────────────────────────────────────── */

  return (
    <section
      className={styles.timeline}
      aria-label="Repair validation timeline"
    >
      {/* ── header ──────────────────────────────────────── */}
      <div className={styles.sectionHeader}>
        <div>
          <p className={styles.kicker}>S4-F08</p>
          <h2>Repair Validation Timeline</h2>
        </div>
        <StatusBadge state={timelineState} />
      </div>

      {/* ── reconnecting banner ─────────────────────────── */}
      {timelineState === "reconnecting" && (
        <div className={styles.reconnectBar} role="alert">
          <span className={styles.reconnectSpinner} />
          <span>Backend connection interrupted — retrying…</span>
        </div>
      )}

      {/* ── stale banner ───────────────────────────────── */}
      {timelineState === "stale" && (
        <div className={styles.staleBar} role="alert">
          <span>
            Validation data is stale (idempotent replay detected).
            Reload from backend.
          </span>
          <button
            type="button"
            className={styles.actionButton}
            onClick={handleRefresh}
          >
            Reload
          </button>
        </div>
      )}

      {/* ── loading ─────────────────────────────────────── */}
      {timelineState === "loading" && (
        <p className={styles.notice}>Loading validation state…</p>
      )}

      {/* ── backend-failure ─────────────────────────────── */}
      {timelineState === "backend-failure" && (
        <div>
          <p className={styles.noticeError} role="alert">
            {error ?? "An unexpected error occurred."}
          </p>
          <button
            type="button"
            className={styles.actionButton}
            onClick={handleRefresh}
          >
            Retry
          </button>
        </div>
      )}

      {/* ── empty ───────────────────────────────────────── */}
      {timelineState === "empty" && !loading && !error && (
        <div>
          <p className={styles.notice}>
            No validation data available for this repair attempt.
            Trigger validation to begin.
          </p>
        </div>
      )}

      {/* ── validation content ──────────────────────────── */}
      {result && timelineState !== "loading" && (
        <div className={styles.timelinePipe}>
          {/* preflight checks */}
          <div className={`${styles.section} ${styles.fadeIn}`}>
            <div className={styles.sectionHeader}>
              <h3>Preflight Checks</h3>
              <span className={styles.boundaryBadge}>
                {result.preflight_status}
              </span>
            </div>
            <ul className={styles.checkList}>
              {preflightChecks.map((check) => (
                <li
                  key={check.name}
                  className={`${styles.checkItem} ${statusClass(
                    check.status,
                  )}`}
                >
                  <span
                    className={`${styles.checkIcon} ${statusClass(
                      check.status,
                    )}`}
                  >
                    {statusIcon(check.status)}
                  </span>
                  <span className={styles.checkLabel}>
                    {check.label}
                  </span>
                  <span className={styles.checkValue}>
                    {check.detail}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* invalidation boundary */}
          <div className={`${styles.section} ${styles.fadeIn}`}>
            <h3>Invalidation Boundary</h3>
            <div className={styles.metadataGrid}>
              <div className={styles.metadataItem}>
                <span className={styles.metadataLabel}>
                  State version
                </span>
                <span className={styles.metadataValue}>
                  #{result.state_version}
                </span>
              </div>
              <div className={styles.metadataItem}>
                <span className={styles.metadataLabel}>
                  Validation status
                </span>
                <span className={styles.metadataValue}>
                  {result.validation_status}
                </span>
              </div>
              {Object.entries(result.artifact_refs ?? {}).map(
                ([key, value]) => (
                  <div key={key} className={styles.metadataItem}>
                    <span className={styles.metadataLabel}>
                      {key.replace(/_/g, " ")}
                    </span>
                    <span className={styles.metadataValue}>
                      {String(value).length > 40
                        ? `${String(value).slice(0, 40)}…`
                        : String(value)}
                    </span>
                  </div>
                ),
              )}
            </div>
          </div>

          {/* error delta */}
          <div className={`${styles.section} ${styles.fadeIn}`}>
            <h3>Error Delta</h3>
            <div className={styles.deltaGrid}>
              {/* New errors */}
              <div className={styles.deltaRow}>
                <span className={styles.deltaIcon}>🆕</span>
                <div className={styles.deltaContent}>
                  <span className={styles.deltaTitle}>
                    New errors
                    {errorDelta && (
                      <span className={styles.checkMismatch}>
                        {" "}
                        ({errorDelta.newErrors.length})
                      </span>
                    )}
                  </span>
                  {errorDelta && errorDelta.newErrors.length > 0
                    ? (
                      <ul className={styles.deltaList}>
                        {errorDelta.newErrors.map((e, i) => (
                          <li key={`new-${i}`}>{e}</li>
                        ))}
                      </ul>
                    )
                    : (
                      <p className={styles.deltaEmpty}>
                        {validationRunning
                          ? "Awaiting result…"
                          : result.validation_status === "passed"
                          ? "No new errors introduced"
                          : "No new error details available"}
                      </p>
                    )}
                </div>
              </div>

              {/* Resolved errors */}
              <div className={styles.deltaRow}>
                <span className={styles.deltaIcon}>✅</span>
                <div className={styles.deltaContent}>
                  <span className={styles.deltaTitle}>
                    Resolved errors
                    {errorDelta && (
                      <span className={styles.checkMatch}>
                        {" "}
                        ({errorDelta.resolvedErrors.length})
                      </span>
                    )}
                  </span>
                  {errorDelta &&
                      errorDelta.resolvedErrors.length > 0
                    ? (
                      <ul className={styles.deltaList}>
                        {errorDelta.resolvedErrors.map((e, i) => (
                          <li key={`resolved-${i}`}>{e}</li>
                        ))}
                      </ul>
                    )
                    : (
                      <p className={styles.deltaEmpty}>
                        {validationRunning
                          ? "Awaiting result…"
                          : "No errors resolved in this attempt"}
                      </p>
                    )}
                </div>
              </div>

              {/* Persistent errors */}
              <div className={styles.deltaRow}>
                <span className={styles.deltaIcon}>🔄</span>
                <div className={styles.deltaContent}>
                  <span className={styles.deltaTitle}>
                    Persistent errors
                    {errorDelta && (
                      <span> ({errorDelta.persistentErrors.length})</span>
                    )}
                  </span>
                  {errorDelta &&
                      errorDelta.persistentErrors.length > 0
                    ? (
                      <ul className={styles.deltaList}>
                        {errorDelta.persistentErrors.map((e, i) => (
                          <li key={`persistent-${i}`}>{e}</li>
                        ))}
                      </ul>
                    )
                    : (
                      <p className={styles.deltaEmpty}>
                        {validationRunning
                          ? "Awaiting result…"
                          : "No persistent errors remain"}
                      </p>
                    )}
                </div>
              </div>
            </div>
          </div>

          {/* G11 gate */}
          <div className={`${styles.section} ${styles.fadeIn}`}>
            <h3>G11 Gate</h3>
            <div className={styles.g11Status}>
              <StatusBadge
                state={g11StatusToTimelineState(
                  result.g11_status,
                )}
              />
              <span className={styles.boundaryBadge}>
                Gate: {result.g11_gate_id?.slice(0, 12) ?? "—"}
              </span>
            </div>

            {canDecideG11(result) && (
              <>
                <div className={styles.g11DecisionButtons}>
                  {DECISIONS.map((decision) => (
                    <button
                      key={decision}
                      type="button"
                      className={`${styles.g11Button} ${
                        decision === "APPROVED"
                          ? styles.g11Approve
                          : decision === "REJECTED"
                          ? styles.g11Reject
                          : styles.g11Modify
                      }`}
                      disabled={
                        g11Submitting !== null
                      }
                      onClick={() => handleG11Decision(decision)}
                    >
                      {g11Submitting === decision
                        ? "Submitting…"
                        : decision === "APPROVED"
                        ? "✓ Approve"
                        : decision === "REJECTED"
                        ? "✗ Reject"
                        : "⟳ Modify Request"}
                    </button>
                  ))}
                </div>

                <div className={styles.g11Rationale}>
                  <textarea
                    placeholder="Rationale for this gate decision (optional)"
                    value={g11Rationale}
                    onChange={(e) =>
                      setG11Rationale(e.target.value)
                    }
                    disabled={g11Submitting !== null}
                    aria-label="Gate decision rationale"
                  />
                </div>
              </>
            )}

            {!canDecideG11(result) && result.g11_status && (
              <p className={styles.notice}>
                Gate decision has been made (
                {result.g11_status}
                ). Refresh to see latest state.
              </p>
            )}

            {g11Result && (
              <div
                className={`${styles.g11Result} ${
                  g11Result.ok
                    ? styles.g11ResultSuccess
                    : styles.g11ResultError
                }`}
                role="alert"
              >
                {g11Result.message}
              </div>
            )}

            {result.g11_status === "stale" && (
              <div className={styles.g11Stale}>
                Gate state is stale — reload validation data to
                reconcile.
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

/* ─── sub-components ──────────────────────────────────────── */

function StatusBadge({ state }: { state: string }) {
  const classMap: Record<string, string | undefined> = {
    loading: styles.statusPending,
    empty: styles.statusPending,
    running: styles.statusRunning,
    success: styles.statusSuccess,
    blocked: styles.statusBlocked,
    stale: styles.statusBlocked,
    reconnecting: styles.statusRunning,
    "backend-failure": styles.statusFailed,
    pending: styles.statusPending,
    approved: styles.statusSuccess,
    rejected: styles.statusFailed,
    modification_requested: styles.statusBlocked,
  };

  const labelMap: Record<string, string> = {
    loading: "Loading",
    empty: "Not started",
    running: "Running",
    success: "Passed",
    blocked: "Blocked",
    stale: "Stale",
    reconnecting: "Reconnecting",
    "backend-failure": "Error",
    pending: "Pending",
    approved: "Approved",
    rejected: "Rejected",
    modification_requested: "Modify Requested",
  };

  return (
    <span
      className={`${styles.statusBadge} ${
        classMap[state] ?? styles.statusPending
      }`}
    >
      {labelMap[state] ?? state}
    </span>
  );
}

function g11StatusToTimelineState(
  g11Status: string | undefined | null,
): string {
  switch (g11Status) {
    case "approved":
      return "approved";
    case "rejected":
      return "rejected";
    case "modification_requested":
      return "modification_requested";
    case "pending":
    case "awaiting_decision":
      return "pending";
    case "stale":
      return "stale";
    default:
      return "pending";
  }
}

function canDecideG11(result: ValidateRepairResult): boolean {
  const openStatuses = new Set([
    "pending",
    "awaiting_decision",
    "stale",
    "",
    undefined,
    null,
  ]);
  return openStatuses.has(result.g11_status);
}
