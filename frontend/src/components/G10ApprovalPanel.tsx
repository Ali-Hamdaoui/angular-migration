"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getG10Package, decideG10 } from "@/api/repair";
import type { G10PackageResponse, G10DecisionValue } from "@/types/repair";
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
  proposalId: string;
  stateVersion: number;
  connectionStatus?: ConnectionStatus;
  refreshState?: () => Promise<unknown>;
  workflowEvents?: Array<{ event_type: string; sequence: number }>;
};

function operationKey(runId: string) {
  return `g10-${runId}-${proposalId}-${Date.now()}`;
}

function formatDecision(d: string) {
  return d.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function connectionLabel(status: Props["connectionStatus"]) {
  if (status === "open") return "Live authoritative G10 state";
  if (status === "reconnecting") return "Connection lost. Reconnecting...";
  if (status === "recovering") return "Refreshing authoritative G10 state...";
  if (status === "failed") return "Unable to refresh authoritative G10 state";
  return "Connecting to authoritative G10 state...";
}

const G10_DECISIONS = ["approve", "reject"] as const;

export function G10ApprovalPanel({
  runId,
  proposalId,
  stateVersion,
  connectionStatus,
  refreshState,
  workflowEvents,
}: Props) {
  const [g10Package, setG10Package] = useState<G10PackageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [correlationId, setCorrelationId] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [rationale, setRationale] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const pkg = await getG10Package(runId, proposalId);
      setG10Package(pkg);
      setStale(false);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError) {
        if (reason.status === 404) {
          setG10Package(null);
          return;
        }
        setError("The G10 package request failed.");
        if (reason.status === 409) setStale(true);
        return;
      }
      setError("G10 package could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [runId, proposalId]);

  useEffect(() => {
    void refresh();
  }, [refresh, stateVersion]);

  const g10Status = useMemo(() => {
    if (workflowEvents?.some((e) => e.event_type === "G10_STALE")) return "stale";
    if (g10Package?.g10_status === "approved") return "approved";
    if (g10Package?.g10_status === "approved_with_comment") return "approved_with_comment";
    if (g10Package?.g10_status === "rejected") return "rejected";
    if (g10Package?.g10_status === "stale") return "stale";
    return g10Package?.g10_status ?? "pending";
  }, [g10Package, workflowEvents]);

  const isResolved = ["approved", "approved_with_comment", "rejected"].includes(g10Status);
  const canDecide = g10Status === "pending" && !working && !stale && g10Package !== null;

  async function handleDecision(decision: string) {
    if (!g10Package) return;
    setWorking(true);
    setError(null);
    setConfirming(null);
    try {
      const result = await decideG10(runId, proposalId, {
        expected_state_version: g10Package.state_version,
        decision: decision as G10DecisionValue,
        actor: "operator",
        rationale: rationale || undefined,
        idempotency_key: operationKey(runId),
        workspace_fingerprint: g10Package.workspace_fingerprint,
        diff_checksum: g10Package.diff_checksum,
        lineage_checksum: g10Package.lineage_checksum,
      });
      setCorrelationId(result.correlation_id ?? null);
      if (result.stale) {
        setStale(true);
        setError("The G10 decision is stale. Refresh the page.");
      } else {
        await refreshState?.();
        await refresh();
      }
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError) {
        const body = reason.responseBody ? JSON.parse(reason.responseBody) : null;
        setError(`G10 decision failed. ${body?.detail?.message ?? reason.statusText}`);
        if (reason.status === 409) setStale(true);
        return;
      }
      setError("G10 decision could not be submitted.");
    } finally {
      setWorking(false);
    }
  }

  if (loading) {
    return (
      <div className={styles.panel}>
        <h3 className={styles.panelTitle}>G10 — Human Apply / Reject</h3>
        <p className={styles.statusMessage}>{connectionLabel(connectionStatus)}</p>
      </div>
    );
  }

  if (!g10Package) {
    return (
      <div className={styles.panel}>
        <h3 className={styles.panelTitle}>G10 — Human Apply / Reject</h3>
        <p className={styles.statusMessage}>No G10 package available. Complete the Proposer and Reviewer steps first.</p>
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <h3 className={styles.panelTitle}>
        G10 — Human Apply / Reject{" "}
        <span className={styles.badge} data-status={g10Status}>
          {formatDecision(g10Status)}
        </span>
      </h3>

      {connectionStatus !== "open" && connectionStatus !== undefined && (
        <p className={styles.statusMessage}>{connectionLabel(connectionStatus)}</p>
      )}

      {error && (
        <div className={styles.errorBlock}>
          <p>{error}</p>
          {correlationId && <p className={styles.correlationId}>Correlation: {correlationId}</p>}
        </div>
      )}

      {stale && (
        <div className={styles.warningBlock}>
          <p>The G10 state is stale. Refresh the page to reload the current state.</p>
          <button className={styles.secondaryButton} onClick={() => { void refresh(); }}>
            Refresh state
          </button>
        </div>
      )}

      {/* Proposal review evidence */}
      <div className={styles.section}>
        <h4>Proposal Evidence</h4>
        <dl className={styles.keyValueList}>
          <dt>Diff checksum</dt>
          <dd><code>{g10Package.diff_checksum}</code></dd>
          <dt>Lineage checksum</dt>
          <dd><code>{g10Package.lineage_checksum}</code></dd>
          <dt>Workspace fingerprint</dt>
          <dd><code>{g10Package.workspace_fingerprint}</code></dd>
          <dt>State version</dt>
          <dd><code>{g10Package.state_version}</code></dd>
        </dl>
      </div>

      {/* Risk warnings */}
      {g10Package.risk_notes && g10Package.risk_notes.length > 0 && (
        <div className={styles.section}>
          <h4>Risk Warnings</h4>
          <ul>
            {g10Package.risk_notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Diff display */}
      {g10Package.diff_content && (
        <div className={styles.section}>
          <h4>Proposed Diff (read-only)</h4>
          <pre className={styles.diffBlock}>
            <code>{g10Package.diff_content}</code>
          </pre>
        </div>
      )}

      {/* Rationale input */}
      <div className={styles.section}>
        <label htmlFor="g10-rationale">Rationale (optional)</label>
        <textarea
          id="g10-rationale"
          className={styles.textarea}
          rows={3}
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          placeholder="Describe the reason for your decision..."
          disabled={working || isResolved}
        />
      </div>

      {/* Decision controls */}
      <div className={styles.actions}>
        {isResolved ? (
          <p className={styles.statusMessage}>
            Decision already submitted: <strong>{formatDecision(g10Status)}</strong>
          </p>
        ) : confirming ? (
          <div className={styles.confirmGroup}>
            <p className={styles.warningBlock}>
              Are you sure you want to <strong>{formatDecision(confirming)}</strong> this repair proposal?
              {confirming === "approve" && " The diff will be bound to the current checksum and state version."}
            </p>
            <div className={styles.buttonRow}>
              <button
                className={styles.primaryButton}
                disabled={working}
                onClick={() => void handleDecision(confirming)}
              >
                {working ? "Submitting..." : `Confirm ${formatDecision(confirming)}`}
              </button>
              <button
                className={styles.secondaryButton}
                disabled={working}
                onClick={() => setConfirming(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className={styles.buttonRow}>
            {G10_DECISIONS.map((decision) => (
              <button
                key={decision}
                className={decision === "approve" ? styles.primaryButton : styles.dangerButton}
                disabled={!canDecide}
                onClick={() => setConfirming(decision)}
              >
                {formatDecision(decision)}
              </button>
            ))}
          </div>
        )}
      </div>

      {working && <p className={styles.statusMessage}>Submitting G10 decision...</p>}
    </div>
  );
}
