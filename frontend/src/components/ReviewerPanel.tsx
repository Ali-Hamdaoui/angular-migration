"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getReviewer, invokeReviewer } from "@/api/repair";
import type {
  ProposerCandidate,
  ReviewDecision,
  ReviewerResponse,
  ReviewerDecisionValue,
} from "@/types/repair";
import styles from "./ControlTowerShell.module.css";

type ConnectionStatus =
  | "loading"
  | "connecting"
  | "open"
  | "reconnecting"
  | "recovering"
  | "failed";

type Props = {
  runId: string;
  repairAttemptId: string;
  stateVersion: number;
  proposerCandidate: ProposerCandidate | null;
  connectionStatus?: ConnectionStatus;
  refreshState?: () => Promise<unknown>;
  workflowEvents?: Array<{ event_type: string; sequence: number }>;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function operationKey(runId: string, attemptId: string) {
  return `reviewer-${runId}-${attemptId}-${Date.now()}`;
}

function formatLabel(value: string) {
  return value.replaceAll("_", " ");
}

function formatCost(value: number | string) {
  const n = typeof value === "string" ? Number(value) : value;
  return `$${n.toFixed(6)}`;
}

function correlationFrom(error: ApiClientError) {
  try {
    const body = JSON.parse(error.responseBody ?? "{}") as {
      correlation_id?: string;
    };
    return body.correlation_id ?? null;
  } catch {
    return null;
  }
}

function connectionLabel(status: ConnectionStatus | undefined) {
  if (status === "open") return "Live authoritative reviewer state";
  if (status === "reconnecting") return "Connection lost. Reconnecting...";
  if (status === "recovering") return "Refreshing authoritative reviewer state...";
  if (status === "failed") return "Unable to refresh reviewer state";
  return "Connecting to reviewer state...";
}

function decisionBadgeClass(decision: ReviewerDecisionValue): string {
  if (decision === "accept") return styles.status;
  // Reuse existing status badge style (visual differentiation via content)
  return styles.status;
}

function decisionEmoji(decision: ReviewerDecisionValue): string {
  switch (decision) {
    case "accept":
      return "\u2705";
    case "request_revision":
      return "\u{1F504}";
    case "reject":
      return "\u274C";
    case "insufficient_context":
      return "\u2753";
  }
}

/* ------------------------------------------------------------------ */
/*  Critique / Revision timeline                                       */
/* ------------------------------------------------------------------ */

function CritiqueList({ critique }: { critique: string[] }) {
  if (!critique.length) return null;
  return (
    <div className={styles.previewPanel}>
      <h3>Critique</h3>
      <ul className={styles.list}>
        {critique.map((item, index) => (
          <li key={index}>
            <span>{formatLabel(item)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RevisionInstructionsList({
  instructions,
}: {
  instructions: string[];
}) {
  if (!instructions.length) return null;
  return (
    <div className={styles.previewPanel}>
      <h3>Revision instructions</h3>
      <ul className={styles.list}>
        {instructions.map((item, index) => (
          <li key={index}>
            <span>{formatLabel(item)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RequestedContextList({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className={styles.previewPanel}>
      <h3>Requested context</h3>
      <ul className={styles.list}>
        {items.map((item, index) => (
          <li key={index}>
            <code>{item}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ReviewerPanel                                                      */
/* ------------------------------------------------------------------ */

export function ReviewerPanel({
  runId,
  repairAttemptId,
  stateVersion,
  proposerCandidate,
  connectionStatus,
  refreshState,
  workflowEvents,
}: Props) {
  const [reviewer, setReviewer] = useState<ReviewerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [correlationId, setCorrelationId] = useState<string | null>(null);

  /* Latest reviewer-related event sequence for re-fetch gating */
  const latestEventSequence = useMemo(() => {
    if (!workflowEvents?.length) return 0;
    return (
      [...workflowEvents]
        .reverse()
        .find((ev) => ev.event_type.startsWith("REVIEWER_"))?.sequence ?? 0
    );
  }, [workflowEvents]);

  /* ---- refresh ---- */

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setEmpty(false);
    setCorrelationId(null);
    try {
      const result = await getReviewer(runId, repairAttemptId);
      setReviewer(result);
      setEmpty(false);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setEmpty(true);
      } else if (reason instanceof ApiClientError) {
        setError(
          `Reviewer data could not be loaded. Correlation ID: ${correlationFrom(reason) ?? "unavailable"}`,
        );
      } else {
        setError("Reviewer data could not be loaded.");
      }
    } finally {
      setLoading(false);
    }
  }, [runId, repairAttemptId]);

  useEffect(() => {
    void refresh();
  }, [refresh, stateVersion, latestEventSequence]);

  /* ---- invoke ---- */

  async function invoke() {
    setWorking(true);
    setError(null);
    setStale(false);
    setCorrelationId(null);
    try {
      const result = await invokeReviewer(runId, repairAttemptId, {
        expected_state_version: stateVersion,
        idempotency_key: operationKey(runId, repairAttemptId),
      });
      setReviewer(result);
      setCorrelationId(result.correlation_id ?? result.review_decision.review_id);
      setEmpty(false);
      await refreshState?.();
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) {
        setStale(true);
        setCorrelationId(correlationFrom(reason));
        await refresh();
      } else if (reason instanceof ApiClientError) {
        setCorrelationId(correlationFrom(reason));
        setError(
          "The Reviewer invocation failed. Review the correlation ID and backend evidence.",
        );
      } else {
        setError("The Reviewer invocation failed.");
      }
    } finally {
      setWorking(false);
    }
  }

  /* ---- derived state ---- */

  const status: ReviewerDecisionValue | null = reviewer?.decision ?? null;
  const running = status === null && !empty && !loading && !error;
  const decision: ReviewDecision | null = reviewer?.review_decision ?? null;
  const isAccepted = status === "accept";
  const isRevisionRequested = status === "request_revision";
  const isRejected = status === "reject";
  const isInsufficientContext = status === "insufficient_context";
  const isBlocked = false; // reviewer has no explicit "blocked" status
  const usage = reviewer?.usage ?? {};
  const revisionCount = reviewer?.revision_count ?? 0;

  /* ---- render ---- */

  return (
    <section className={styles.panel} aria-labelledby="reviewer-panel-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S4-F05</p>
          <h2 id="reviewer-panel-title">Reviewer — non-authoring AI review</h2>
          <p className={styles.note}>
            The Reviewer evaluates the proposer candidate diff and returns a
            decision with critique. The Reviewer <strong>never authors a
            diff</strong> — only the Proposer may do that.
          </p>
        </div>
        <span className={styles.status}>
          {status ? `${decisionEmoji(status)} ${formatLabel(status)}` : "not loaded"}
        </span>
      </div>

      {connectionStatus ? (
        <div className={styles.connectionBar} role="status" aria-live="polite">
          {connectionLabel(connectionStatus)}
        </div>
      ) : null}

      {loading ? <p role="status">Loading reviewer result...</p> : null}

      {error ? <p role="alert">{error}</p> : null}

      {stale ? (
        <p role="alert">
          The run changed while the reviewer was being invoked. Refresh the
          authoritative state before retrying.
        </p>
      ) : null}

      {/* ---- No proposer candidate ---- */}
      {!loading && !empty && !proposerCandidate && !reviewer ? (
        <p className={styles.note}>
          No proposer candidate is available yet. The Reviewer requires a
          proposer candidate before it can produce a review.
        </p>
      ) : null}

      {/* ---- Empty / not yet invoked ---- */}
      {!loading && empty && proposerCandidate ? (
        <>
          <p className={styles.note}>
            No reviewer result is available for this repair attempt yet.
          </p>
          <div className={styles.previewHeader}>
            <span className={styles.note}>
              Invoking the Reviewer will evaluate the proposer candidate diff
              and produce a decision with critique.
            </span>
            <button
              type="button"
              onClick={() => void invoke()}
              disabled={working || loading}
            >
              {working ? "Invoking Reviewer..." : "Invoke Reviewer"}
            </button>
          </div>
        </>
      ) : null}

      {/* ---- Reviewer never authors a diff notice ---- */}
      {reviewer ? (
        <div className={styles.previewPanel}>
          <p role="status" className={styles.note}>
            <strong>Notice:</strong> The Reviewer never authors a diff. The
            review decision is bound to the proposer candidate diff checksum:
            <code> {decision?.proposal_diff_checksum ?? "unavailable"}</code>
          </p>
        </div>
      ) : null}

      {/* ---- In progress / running ---- */}
      {running && reviewer ? (
        <p role="status">
          The Reviewer is evaluating the proposer candidate. Refresh the
          authoritative event and snapshot for the latest state.
        </p>
      ) : null}

      {/* ---- Decision display ---- */}
      {reviewer && decision ? (
        <>
          {/* Side-by-side: Proposer candidate summary + Reviewer decision */}
          {proposerCandidate ? (
            <div className={styles.twoColumns}>
              {/* Proposer Candidate column */}
              <div className={styles.previewPanel}>
                <h3>Proposer candidate</h3>
                {proposerCandidate.changed_files.length > 0 ? (
                  <>
                    <h4>Changed files</h4>
                    <ul className={styles.list}>
                      {proposerCandidate.changed_files.map((file) => (
                        <li key={file}>
                          <code>{file}</code>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
                {proposerCandidate.risk_notes.length > 0 ? (
                  <>
                    <h4>Risk notes</h4>
                    <ul className={styles.list}>
                      {proposerCandidate.risk_notes.map((note, index) => (
                        <li key={index}>
                          <span>{formatLabel(note)}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
                <p className={styles.note}>
                  Diff checksum: <code>{proposerCandidate.diff_checksum}</code>
                </p>
              </div>

              {/* Reviewer Decision column */}
              <div className={styles.previewPanel}>
                <h3>
                  Reviewer decision{" "}
                  <span className={decisionBadgeClass(decision.decision)}>
                    {decisionEmoji(decision.decision)}{" "}
                    {formatLabel(decision.decision)}
                  </span>
                </h3>
                <CritiqueList critique={decision.critique} />
                <RevisionInstructionsList
                  instructions={decision.revision_instructions}
                />
                <RequestedContextList items={decision.requested_context} />
                <p className={styles.note}>
                  Review checksum: <code>{decision.review_checksum}</code>
                </p>
              </div>
            </div>
          ) : (
            /* No proposer candidate — show just the review decision */
            <div className={styles.previewPanel}>
              <h3>
                Reviewer decision{" "}
                <span className={decisionBadgeClass(decision.decision)}>
                  {decisionEmoji(decision.decision)}{" "}
                  {formatLabel(decision.decision)}
                </span>
              </h3>
              <CritiqueList critique={decision.critique} />
              <RevisionInstructionsList
                instructions={decision.revision_instructions}
              />
              <RequestedContextList items={decision.requested_context} />
              <p className={styles.note}>
                Review checksum: <code>{decision.review_checksum}</code>
              </p>
            </div>
          )}

          {/* Revision timeline */}
          {revisionCount > 0 ? (
            <div className={styles.previewPanel}>
              <h3>Revision timeline</h3>
              <p className={styles.note}>
                The Reviewer completed {revisionCount} revision
                {revisionCount !== 1 ? "s" : ""} before reaching the final
                decision.
              </p>
              {decision.revision_instructions.length > 0 ? (
                <ul className={styles.list}>
                  {decision.revision_instructions.map((inst, index) => (
                    <li key={index}>
                      <span>
                        Revision {index + 1}: {formatLabel(inst)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}

      {/* ---- Model provenance & usage ---- */}
      {reviewer ? (
        <div className={styles.previewPanel}>
          <h3>Model provenance &amp; usage</h3>
          <div
            className={styles.metadataGrid}
            aria-label="Reviewer provenance"
          >
            <div>
              <dt>Provider</dt>
              <dd>
                {reviewer.model_provenance.provider ?? "unknown"}
              </dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{reviewer.model_provenance.role ?? "repair_reviewer"}</dd>
            </div>
            <div>
              <dt>Prompt version</dt>
              <dd>{reviewer.prompt_version ?? "unknown"}</dd>
            </div>
            <div>
              <dt>Schema version</dt>
              <dd>{reviewer.schema_version ?? "unknown"}</dd>
            </div>
            <div>
              <dt>State version</dt>
              <dd>{reviewer.state_version}</dd>
            </div>
            <div>
              <dt>Event sequence</dt>
              <dd>{reviewer.event_sequence}</dd>
            </div>
            <div>
              <dt>Revision count</dt>
              <dd>{revisionCount}</dd>
            </div>
          </div>
          <ul className={styles.metricList} aria-label="Reviewer usage">
            <li>
              <span>Input tokens</span>
              <strong>
                {Number(usage.input_tokens ?? 0).toLocaleString()}
              </strong>
            </li>
            <li>
              <span>Output tokens</span>
              <strong>
                {Number(usage.output_tokens ?? 0).toLocaleString()}
              </strong>
            </li>
            <li>
              <span>Total tokens</span>
              <strong>
                {Number(usage.total_tokens ?? 0).toLocaleString()}
              </strong>
            </li>
            <li>
              <span>Estimated input cost</span>
              <strong>{formatCost(usage.input_cost_usd ?? 0)}</strong>
            </li>
            <li>
              <span>Estimated output cost</span>
              <strong>{formatCost(usage.output_cost_usd ?? 0)}</strong>
            </li>
            <li>
              <span>Estimated total cost</span>
              <strong>{formatCost(usage.total_cost_usd ?? 0)}</strong>
            </li>
          </ul>
        </div>
      ) : null}

      {/* ---- Artifact links ---- */}
      {reviewer?.artifact_ids?.length ? (
        <div className={styles.previewPanel}>
          <h3>Immutable evidence artifacts</h3>
          <p className={styles.note}>
            Registered artifact IDs and checksums from the backend snapshot.
          </p>
          <ul className={styles.list}>
            {reviewer.artifact_ids.map((id) => (
              <li key={id}>
                <a
                  className={styles.actionLink}
                  href={
                    reviewer.artifact_links[id] ??
                    `/api/v1/artifacts/${encodeURIComponent(id)}`
                  }
                  target="_blank"
                  rel="noreferrer"
                >
                  {id}
                </a>
                <code>{reviewer.artifact_checksums[id]}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* ---- Correlation / invocation ID ---- */}
      {correlationId ? (
        <p className={styles.note}>
          Correlation / invocation ID: <code>{correlationId}</code>
        </p>
      ) : null}
      {reviewer?.correlation_id ? (
        <p className={styles.note}>
          Backend correlation ID: <code>{reviewer.correlation_id}</code>
        </p>
      ) : null}

      {/* ---- Idempotent replay indicator ---- */}
      {reviewer?.idempotent_replay ? (
        <p role="status" className={styles.note}>
          This result is a replay of a prior invocation (idempotent).
        </p>
      ) : null}

      {/* ---- Invoke button when we have results but not empty ---- */}
      {!loading && !empty && reviewer && proposerCandidate ? (
        <div className={styles.previewHeader}>
          <span className={styles.note}>
            The frontend never advances the workflow locally. Re-invoke the
            Reviewer to regenerate the review decision.
          </span>
          <button
            type="button"
            onClick={() => void invoke()}
            disabled={working || loading}
          >
            {working ? "Invoking..." : "Re-invoke Reviewer"}
          </button>
        </div>
      ) : null}
    </section>
  );
}
