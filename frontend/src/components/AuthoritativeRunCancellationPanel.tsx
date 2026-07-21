"use client";

import { useState } from "react";
import { ApiClientError } from "@/api/client";
import { cancelAuthoritativeRun } from "@/api/runs";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

const ACTIVE_STATUSES = new Set([
  "CREATED", "SOURCE_VALIDATED", "WAITING",
]);

function errorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    try {
      const body = JSON.parse(error.responseBody ?? "{}") as { message?: string; detail?: string };
      return body.message ?? body.detail ?? `${error.message}.`;
    } catch { return error.responseBody || error.message; }
  }
  return "The run could not be cancelled. Refresh the run state and retry.";
}

export function AuthoritativeRunCancellationPanel({
  runId, state, refresh,
}: { runId: string; state: AuthoritativeRunStateDto; refresh: () => Promise<unknown> }) {
  const [confirming, setConfirming] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancellable = ACTIVE_STATUSES.has(state.status);

  async function cancel() {
    setCancelling(true); setError(null);
    try {
      await cancelAuthoritativeRun(runId, {
        expected_state_version: state.state_version,
        idempotency_key: `run-cancel-${runId}-${state.state_version}`,
        actor: "control-tower",
      });
      setConfirming(false);
      await refresh();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setCancelling(false); }
  }

  if (!cancellable) return null;
  return <section className={`${styles.panel} ${styles.dangerPanel}`} aria-labelledby="cancel-run-title">
    <p className={styles.kicker}>Run controls</p>
    <h2 id="cancel-run-title">Cancel migration</h2>
    <p className={styles.note}>Cancellation retains evidence and the workspace, then releases this run’s exclusive migration claim.</p>
    {!confirming ? <button className={styles.dangerButton} type="button" onClick={() => setConfirming(true)}>Cancel run</button> : <div className={styles.cancelConfirm} role="alert">
      <p>Cancel this run? It cannot be resumed after cancellation.</p>
      <div><button type="button" disabled={cancelling} onClick={() => setConfirming(false)}>Keep run</button><button className={styles.dangerButton} type="button" disabled={cancelling} onClick={() => void cancel()}>{cancelling ? "Cancelling…" : "Confirm cancellation"}</button></div>
    </div>}
    {error ? <p className={styles.dangerMessage} role="alert">{error}</p> : null}
  </section>;
}
