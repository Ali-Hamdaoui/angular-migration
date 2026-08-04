"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { cancelBaselineValidation, getBaselineTargets, getBaselineValidation, startBaselineValidation } from "@/api/baselineMatrix";
import type { BaselineMatrixKind, BaselineMatrixResult, BaselineTargetInventoryResponse, BaselineValidationResponse } from "@/types/baselineMatrix";
import styles from "./ControlTowerShell.module.css";

const kinds: BaselineMatrixKind[] = ["build", "test", "lint"];
type ConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";
function operationKey(runId: string, kind: BaselineMatrixKind) { return `baseline-matrix-${kind}-${runId}-${Date.now()}`; }
function label(value: string) { return value.replaceAll("_", " "); }
function resultFor(results: BaselineMatrixResult[], targetId: string) { return results.find((item) => item.target_id === targetId); }
const terminal = new Set(["passed", "failed", "skipped_not_configured", "skipped_not_applicable", "blocked", "interrupted", "cancelled"]);

export function BaselineValidationPanel({ runId, stateVersion, connectionStatus, availableKinds = kinds }: { runId: string; stateVersion: number; connectionStatus: ConnectionStatus; availableKinds?: BaselineMatrixKind[] }) {
  const [inventory, setInventory] = useState<BaselineTargetInventoryResponse | null>(null);
  const [validations, setValidations] = useState<Partial<Record<BaselineMatrixKind, BaselineValidationResponse>>>({});
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<BaselineMatrixKind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [targets, ...results] = await Promise.all([getBaselineTargets(runId), ...availableKinds.map((kind) => getBaselineValidation(runId, kind).catch((reason: unknown) => reason instanceof ApiClientError && reason.status === 404 ? null : Promise.reject(reason)))]);
      setInventory(targets);
      setValidations(Object.fromEntries(results.filter((item): item is BaselineValidationResponse => item !== null).map((item) => [item.kind, item])));
    } catch { setError("Baseline validation evidence could not be loaded."); }
    finally { setLoading(false); }
  }, [availableKinds, runId]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion]);
  useEffect(() => {
    if (!Object.values(validations).some((item) => item?.status === "running")) return;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [refresh, validations]);

  async function start(kind: BaselineMatrixKind) {
    setWorking(kind); setError(null); setStale(false);
    try {
      const result = await startBaselineValidation(runId, kind, { expected_state_version: stateVersion, idempotency_key: operationKey(runId, kind), actor: "control-tower" });
      setValidations((current) => ({ ...current, [kind]: result }));
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true); else setError(`The baseline ${kind} validation could not be started.`);
    } finally { setWorking(null); }
  }

  async function cancel(kind: BaselineMatrixKind) {
    setWorking(kind); setError(null);
    try { const result = await cancelBaselineValidation(runId, kind); setValidations((current) => ({ ...current, [kind]: result })); }
    catch { setError(`The baseline ${kind} cancellation request could not be completed.`); }
    finally { setWorking(null); }
  }

  const connectionLabel = connectionStatus === "open" ? "Live baseline validation state" : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..." : connectionStatus === "recovering" ? "Refreshing authoritative validation state..." : connectionStatus === "failed" ? "Unable to refresh validation state" : "Connecting to validation events...";
  const targetsByKind = useMemo(() => kinds.map((kind) => ({ kind, targets: inventory?.targets.filter((target) => target.kind === kind) ?? [] })), [inventory]);
  return <section className={styles.panel} aria-labelledby="baseline-validation-title">
    <div className={styles.header}><div><p className={styles.kicker}>Baseline checks</p><h2 id="baseline-validation-title">Baseline checks</h2><p className={styles.note}>Authoritative target status and evidence from the clean baseline sandbox.</p></div><span className={styles.status}>{inventory ? "discovered" : "not loaded"}</span></div>
    <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>
    {loading ? <p role="status">Loading baseline validation targets...</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {stale ? <p role="alert">The run changed while validation was requested. Refresh the authoritative state before retrying.</p> : null}
    {!loading && !inventory ? <p className={styles.note}>No baseline validation targets have been discovered.</p> : null}
    {targetsByKind.map(({ kind, targets }) => { const validation = validations[kind]; const running = validation?.status === "running"; return <div className={styles.previewPanel} key={kind}>
      <div className={styles.previewHeader}><h3>{kind} targets</h3>{targets.length > 0 && (running ? <button type="button" onClick={() => void cancel(kind)} disabled={working !== null}>{working === kind ? "Cancelling..." : "Cancel"}</button> : <button type="button" onClick={() => void start(kind)} disabled={working !== null}>{working === kind ? "Starting..." : validation && !terminal.has(validation.status) ? `Retry ${kind}` : `Run ${kind}`}</button>)}</div>
      {targets.length === 0 ? <p className={styles.note}>No {kind} target configured.</p> : <ul className={styles.list}>{targets.map((target) => { const result = validation ? resultFor(validation.results, target.target_id) : undefined; const status = result?.status ?? (target.supported ? "not_started" : target.blocker === "NOT_CONFIGURED" ? "skipped_not_configured" : "blocked"); return <li key={target.target_id}><code>{target.target_id}</code><span>{target.executable ? `${target.executable} ${target.arguments.join(" ")}` : target.blocker}</span><strong>{label(status)}</strong>{result ? <small>{result.duration_ms ?? 0} ms · {result.warnings.length} warnings · {result.test_count ?? 0} tests · {result.artifact_ids.length} artifacts</small> : null}{result?.failed_tests.length ? <small role="alert">Failed: {result.failed_tests.join(", ")}</small> : null}</li>; })}</ul>}
      {validation ? <p className={styles.note}>Status {label(validation.status)} · state version {validation.state_version} · event sequence {validation.event_sequence} · {validation.artifact_ids.length} artifacts.</p> : null}
    </div>; })}
  </section>;
}
