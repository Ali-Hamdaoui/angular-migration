"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getBaselineTargets, getBaselineValidation, startBaselineValidation } from "@/api/baselineMatrix";
import type { AuthoritativeConnectionStatus, } from "@/hooks/useAuthoritativeRun";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { BaselineMatrixKind, BaselineMatrixResult, BaselineTargetInventoryResponse, BaselineValidationResponse } from "@/types/baselineMatrix";
import styles from "./ControlTowerShell.module.css";

const kinds: BaselineMatrixKind[] = ["build", "test", "lint"];

function operationKey(runId: string, kind: BaselineMatrixKind) { return `baseline-matrix-${kind}-${runId}-${Date.now()}`; }
function label(value: string) { return value.replaceAll("_", " "); }
function resultFor(results: BaselineMatrixResult[], targetId: string) { return results.find((item) => item.target_id === targetId); }

export function BaselineValidationPanel({ runId, initialState, connectionStatus }: { runId: string; initialState: AuthoritativeRunStateDto; connectionStatus: AuthoritativeConnectionStatus }) {
  const [inventory, setInventory] = useState<BaselineTargetInventoryResponse | null>(null);
  const [validations, setValidations] = useState<Partial<Record<BaselineMatrixKind, BaselineValidationResponse>>>({});
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<BaselineMatrixKind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [targets, ...results] = await Promise.all([getBaselineTargets(runId), ...kinds.map((kind) => getBaselineValidation(runId, kind).catch((reason: unknown) => reason instanceof ApiClientError && reason.status === 404 ? null : Promise.reject(reason)))]);
      setInventory(targets); setValidations(Object.fromEntries(results.filter((item): item is BaselineValidationResponse => item !== null).map((item) => [item.kind, item])));
    } catch { setError("Baseline validation evidence could not be loaded."); }
    finally { setLoading(false); }
  }, [runId]);

  useEffect(() => { void refresh(); }, [refresh, initialState.state_version]);

  async function start(kind: BaselineMatrixKind) {
    setWorking(kind); setError(null); setStale(false);
    try {
      const result = await startBaselineValidation(runId, kind, { expected_state_version: initialState.state_version, idempotency_key: operationKey(runId, kind), actor: "control-tower" });
      setValidations((current) => ({ ...current, [kind]: result }));
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError(`The baseline ${kind} validation could not be started.`);
    } finally { setWorking(null); }
  }

  const connectionLabel = connectionStatus === "open" ? "Live baseline validation state" : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..." : connectionStatus === "recovering" ? "Refreshing authoritative validation state..." : connectionStatus === "failed" ? "Unable to refresh validation state" : "Connecting to validation events...";
  const targetsByKind = useMemo(() => kinds.map((kind) => ({ kind, targets: inventory?.targets.filter((target) => target.kind === kind) ?? [] })), [inventory]);
  return <section className={styles.panel} aria-labelledby="baseline-validation-title">
    <div className={styles.header}><div><p className={styles.kicker}>S1-F12-I03</p><h2 id="baseline-validation-title">Baseline build, test, and lint matrix</h2><p className={styles.note}>Authoritative target status and evidence from the clean baseline sandbox.</p></div><span className={styles.status}>{inventory ? "discovered" : "not loaded"}</span></div>
    <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>
    {loading ? <p role="status">Loading baseline validation targets...</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {stale ? <p role="alert">The run changed while validation was requested. Refresh the authoritative state before retrying.</p> : null}
    {!loading && !inventory ? <p className={styles.note}>No baseline validation targets have been discovered.</p> : null}
    {targetsByKind.map(({ kind, targets }) => { const validation = validations[kind]; return <div className={styles.previewPanel} key={kind}><div className={styles.previewHeader}><h3>{kind} targets</h3><button type="button" disabled={working !== null || targets.length === 0} onClick={() => void start(kind)}>{working === kind ? "Starting..." : `Run ${kind}`}</button></div>{targets.length === 0 ? <p className={styles.note}>No {kind} target configured.</p> : <ul className={styles.list}>{targets.map((target) => { const result = validation ? resultFor(validation.results, target.target_id) : undefined; const status = result?.status ?? (target.supported ? "not_started" : target.blocker === "NOT_CONFIGURED" ? "skipped_not_configured" : "blocked"); return <li key={target.target_id}><code>{target.target_id}</code><span>{target.executable ? `${target.executable} ${target.arguments.join(" ")}` : target.blocker}</span><strong>{label(status)}</strong>{result?.artifact_ids ? null : null}</li>; })}</ul>}{validation ? <p className={styles.note}>State version {validation.state_version}; event sequence {validation.event_sequence}; artifacts {validation.artifact_ids.length}.</p> : null}</div>; })}
  </section>;
}
