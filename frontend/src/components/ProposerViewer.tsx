"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getProposer, invokeProposer } from "@/api/repair";
import type { ProposerCandidate, ProposerDiagnosis, ProposerResponse } from "@/types/repair";
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
  connectionStatus?: ConnectionStatus;
  refreshState?: () => Promise<unknown>;
  workflowEvents?: Array<{ event_type: string; sequence: number }>;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function operationKey(runId: string, attemptId: string) {
  return `proposer-${runId}-${attemptId}-${Date.now()}`;
}

function formatCost(value: number | string) {
  const n = typeof value === "string" ? Number(value) : value;
  return `$${n.toFixed(6)}`;
}

function formatLabel(value: string) {
  return value.replaceAll("_", " ");
}

function label(value: string) {
  return value.replaceAll("_", " ");
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
  if (status === "open") return "Live authoritative proposer state";
  if (status === "reconnecting") return "Connection lost. Reconnecting...";
  if (status === "recovering") return "Refreshing authoritative proposer state...";
  if (status === "failed") return "Unable to refresh proposer state";
  return "Connecting to proposer state...";
}

/* ------------------------------------------------------------------ */
/*  Diff line renderer (UnifiedDiffViewer-style inline)                */
/* ------------------------------------------------------------------ */

function diffClass(line: string): string {
  if (line.startsWith("---") || line.startsWith("+++")) return styles.diff_file;
  if (line.startsWith("@")) return styles.diff_hunk;
  if (line.startsWith("+")) return styles.diff_add;
  if (line.startsWith("-")) return styles.diff_remove;
  return styles.diff_context;
}

function DiffViewer({ diff }: { diff: string }) {
  const lines = diff.split("\n");
  return (
    <div className={styles.diffViewer} role="region" aria-label="Proposed diff">
      {lines.map((line, index) => (
        <span key={index} className={diffClass(line)}>
          <span className={styles.lineNumber}>{index + 1}</span>
          {line}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ProposerViewer                                                    */
/* ------------------------------------------------------------------ */

export function ProposerViewer({
  runId,
  repairAttemptId,
  stateVersion,
  connectionStatus,
  refreshState,
  workflowEvents,
}: Props) {
  const [proposer, setProposer] = useState<ProposerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [correlationId, setCorrelationId] = useState<string | null>(null);

  /* Latest proposer-related event sequence for re-fetch gating */
  const latestEventSequence = (() => {
    if (!workflowEvents?.length) return 0;
    return [...workflowEvents]
      .reverse()
      .find(
        (ev) =>
          ev.event_type.startsWith("PROPOSER_"),
      )?.sequence ?? 0;
  })();

  /* ---- refresh ---- */

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setEmpty(false);
    setCorrelationId(null);
    try {
      const result = await getProposer(runId, repairAttemptId);
      setProposer(result);
      setEmpty(false);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setEmpty(true);
      } else if (reason instanceof ApiClientError) {
        setError(
          `Proposer data could not be loaded. Correlation ID: ${correlationFrom(reason) ?? "unavailable"}`,
        );
      } else {
        setError("Proposer data could not be loaded.");
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
      const result = await invokeProposer(runId, repairAttemptId, {
        expected_state_version: stateVersion,
        idempotency_key: operationKey(runId, repairAttemptId),
      });
      setProposer(result);
      setCorrelationId(result.correlation_id ?? result.proposer_id);
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
          "The Proposer invocation failed. Review the correlation ID and backend evidence.",
        );
      } else {
        setError("The Proposer invocation failed.");
      }
    } finally {
      setWorking(false);
    }
  }

  /* ---- derived state ---- */

  const status: string | null = proposer?.status ?? null;
  const running = status === "in_progress" || working;
  const candidate: ProposerCandidate | null = proposer?.candidate ?? null;
  const diagnosis: ProposerDiagnosis | null = proposer?.diagnosis ?? null;
  const isCandidate = status === "candidate";
  const isInsufficientContext = status === "insufficient_context";
  const isNotRepairable = status === "not_repairable";
  const isBlocked = status === "blocked" || status === "failed";
  const usage = proposer?.usage ?? {};

  /* ---- render ---- */

  return (
    <section className={styles.panel} aria-labelledby="proposer-viewer-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S4-F04</p>
          <h2 id="proposer-viewer-title">Proposer repair candidate</h2>
          <p className={styles.note}>
            AI-generated diagnosis and candidate diff for the repair attempt.
            The proposal is untrusted until validated and accepted.
          </p>
        </div>
        <span className={styles.status}>{status ?? "not loaded"}</span>
      </div>

      {connectionStatus ? (
        <div className={styles.connectionBar} role="status" aria-live="polite">
          {connectionLabel(connectionStatus)}
        </div>
      ) : null}

      {loading ? <p role="status">Loading proposer result...</p> : null}

      {error ? <p role="alert">{error}</p> : null}

      {stale ? (
        <p role="alert">
          The run changed while the proposer was being invoked. Refresh the
          authoritative state before retrying.
        </p>
      ) : null}

      {/* ---- Empty / not yet invoked ---- */}
      {!loading && empty ? (
        <>
          <p className={styles.note}>
            No proposer result is available for this repair attempt yet.
          </p>
          <div className={styles.previewHeader}>
            <span className={styles.note}>
              Invoking the Proposer will generate a diagnosis and candidate diff
              from the failure evidence.
            </span>
            <button
              type="button"
              onClick={() => void invoke()}
              disabled={working || loading}
            >
              {working ? "Invoking Proposer..." : "Invoke Proposer"}
            </button>
          </div>
        </>
      ) : null}

      {/* ---- In progress ---- */}
      {running && proposer ? (
        <p role="status">
          The Proposer is analyzing the failure evidence. Refresh the
          authoritative event and snapshot for the latest state.
        </p>
      ) : null}

      {/* ---- Blocked / failed ---- */}
      {isBlocked && proposer ? (
        <p role="alert">
          The Proposer returned {formatLabel(status)}. Review the backend
          evidence for details.
        </p>
      ) : null}

      {/* ---- Non-candidate terminal statuses ---- */}
      {isInsufficientContext ? (
        <p role="alert">
          The Proposer determined there is insufficient context to produce a
          repair candidate.
        </p>
      ) : null}

      {isNotRepairable ? (
        <p role="alert">
          The Proposer determined the failure is not repairable through the
          automated process.
        </p>
      ) : null}

      {/* ---- Candidate: full display ---- */}
      {isCandidate && proposer && diagnosis ? (
        <>
          {/* Diagnosis / Evidence */}
          <div className={styles.twoColumns}>
            <div className={styles.previewPanel}>
              <h3>Diagnosis</h3>
              <p>{formatLabel(diagnosis.root_cause)}</p>
              {diagnosis.evidence_references.length > 0 ? (
                <>
                  <h4>Evidence references</h4>
                  <ul className={styles.list}>
                    {diagnosis.evidence_references.map((ref) => (
                      <li key={ref}>
                        <code>{ref}</code>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              <p className={styles.note}>
                Confidence: {formatLabel(diagnosis.confidence)}
              </p>
              <p className={styles.note}>
                Input checksum:{" "}
                <code>{diagnosis.deterministic_input_checksum}</code>
              </p>
            </div>

            <div className={styles.previewPanel}>
              <h3>Strategy</h3>
              <p>{formatLabel(diagnosis.fix_strategy)}</p>
            </div>
          </div>

          {/* Changed files */}
          {candidate?.changed_files.length ? (
            <div className={styles.previewPanel}>
              <h3>Changed files</h3>
              <ul className={styles.list}>
                {candidate.changed_files.map((file) => (
                  <li key={file}>
                    <code>{file}</code>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Risk notes */}
          {candidate?.risk_notes.length ? (
            <div className={styles.previewPanel}>
              <h3>Risk notes</h3>
              <ul className={styles.list}>
                {candidate.risk_notes.map((note, index) => (
                  <li key={index}>
                    <span>{formatLabel(note)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Validation notes (errors/warnings) */}
          {candidate?.validation_notes.length ? (
            <div className={styles.previewPanel}>
              <h3>Validation notes</h3>
              <ul className={styles.list}>
                {candidate.validation_notes.map((note, index) => (
                  <li key={index}>
                    <span role="alert">{formatLabel(note)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Diffs */}
          {candidate?.diff_content ? (
            <div className={styles.previewPanel}>
              <h3>Read-only diff</h3>
              <p className={styles.note}>
                Diff checksum: <code>{candidate.diff_checksum}</code>
              </p>
              <DiffViewer diff={candidate.diff_content} />
            </div>
          ) : null}
        </>
      ) : null}

      {/* ---- Model provenance & usage ---- */}
      {proposer && candidate ? (
        <div className={styles.previewPanel}>
          <h3>Model provenance &amp; usage</h3>
          <div
            className={styles.metadataGrid}
            aria-label="Proposer provenance"
          >
            <div>
              <dt>Provider</dt>
              <dd>
                {proposer.model_provenance.provider ?? "unknown"}
              </dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{proposer.model_provenance.role ?? "repair_proposer"}</dd>
            </div>
            <div>
              <dt>Prompt version</dt>
              <dd>{proposer.prompt_version ?? "unknown"}</dd>
            </div>
            <div>
              <dt>Schema version</dt>
              <dd>{proposer.schema_version ?? "unknown"}</dd>
            </div>
            <div>
              <dt>State version</dt>
              <dd>{proposer.state_version}</dd>
            </div>
            <div>
              <dt>Event sequence</dt>
              <dd>{proposer.event_sequence}</dd>
            </div>
          </div>
          <ul className={styles.metricList} aria-label="Proposer usage">
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
      {proposer?.artifact_ids?.length ? (
        <div className={styles.previewPanel}>
          <h3>Immutable evidence artifacts</h3>
          <p className={styles.note}>
            Registered artifact IDs and checksums from the backend snapshot.
          </p>
          <ul className={styles.list}>
            {proposer.artifact_ids.map((id) => (
              <li key={id}>
                <a
                  className={styles.actionLink}
                  href={
                    proposer.artifact_links[id] ??
                    `/api/v1/artifacts/${encodeURIComponent(id)}`
                  }
                  target="_blank"
                  rel="noreferrer"
                >
                  {id}
                </a>
                <code>{proposer.artifact_checksums[id]}</code>
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
      {proposer?.correlation_id ? (
        <p className={styles.note}>
          Backend correlation ID: <code>{proposer.correlation_id}</code>
        </p>
      ) : null}

      {/* ---- Idempotent replay indicator ---- */}
      {proposer?.idempotent_replay ? (
        <p role="status" className={styles.note}>
          This result is a replay of a prior invocation (idempotent).
        </p>
      ) : null}

      {/* ---- Invoke button when we have results but not empty ---- */}
      {!loading && !empty && !running && !isBlocked ? (
        <div className={styles.previewHeader}>
          <span className={styles.note}>
            The frontend never advances the workflow locally. Re-invoke the
            Proposer to regenerate the candidate.
          </span>
          <button
            type="button"
            onClick={() => void invoke()}
            disabled={working || loading}
          >
            {working ? "Invoking..." : "Re-invoke Proposer"}
          </button>
        </div>
      ) : null}
    </section>
  );
}
