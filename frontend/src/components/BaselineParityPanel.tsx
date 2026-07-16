"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiClientError } from "@/api/client";
import { captureBaselineParity, getBaselineParitySection } from "@/api/baselineParity";
import type { BaselineParityResponse } from "@/types/baselineParity";
import styles from "./ControlTowerShell.module.css";

type ConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";
type Section = "failures" | "routes" | "backend-integration" | "anchors";
const sections: Array<{ id: Section; label: string }> = [
  { id: "failures", label: "Known failures" },
  { id: "routes", label: "Routes" },
  { id: "backend-integration", label: "Backend integration" },
  { id: "anchors", label: "Anchors" },
];

function operationKey(runId: string) { return `baseline-parity-${runId}-${Date.now()}`; }
function label(value: string) { return value.replaceAll("_", " "); }

export function BaselineParityPanel({ runId, stateVersion, connectionStatus }: { runId: string; stateVersion: number; connectionStatus: ConnectionStatus }) {
  const [evidence, setEvidence] = useState<Partial<Record<Section, BaselineParityResponse>>>({});
  const [active, setActive] = useState<Section>("failures");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    const results = await Promise.all(sections.map(async ({ id }) => {
      try { return [id, await getBaselineParitySection(runId, id)] as const; }
      catch (reason: unknown) { if (reason instanceof ApiClientError && reason.status === 404) return [id, null] as const; throw reason; }
    }));
    setEvidence(Object.fromEntries(results.filter((item): item is readonly [Section, BaselineParityResponse] => item[1] !== null)));
    setLoading(false);
  }, [runId]);

  useEffect(() => { void refresh().catch(() => { setError("Baseline parity evidence could not be loaded."); setLoading(false); }); }, [refresh, stateVersion]);

  async function capture() {
    setWorking(true); setError(null); setStale(false);
    try { await captureBaselineParity(runId, { expected_state_version: stateVersion, idempotency_key: operationKey(runId), actor: "control-tower" }); await refresh(); }
    catch (reason: unknown) { if (reason instanceof ApiClientError && reason.status === 409) setStale(true); else setError("Baseline parity evidence could not be captured."); }
    finally { setWorking(false); }
  }

  const current = evidence[active];
  const connectionLabel = connectionStatus === "open" ? "Live baseline parity state" : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..." : connectionStatus === "recovering" ? "Refreshing authoritative parity state..." : connectionStatus === "failed" ? "Unable to refresh parity state" : "Connecting to parity evidence...";
  return <section className={styles.panel} aria-labelledby="baseline-parity-title">
    <div className={styles.header}><div><p className={styles.kicker}>S1-F13</p><h2 id="baseline-parity-title">Baseline parity anchors</h2><p className={styles.note}>Structural evidence and known baseline failures; this is not a functional parity conclusion.</p></div><span className={styles.status}>{Object.keys(evidence).length ? "captured" : "not captured"}</span></div>
    <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>
    {loading ? <p role="status">Loading baseline parity evidence...</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {stale ? <p role="alert">The run changed while parity evidence was requested. Refresh the authoritative state before retrying.</p> : null}
    {!loading && !Object.keys(evidence).length ? <div className={styles.previewPanel}><p className={styles.note}>No parity evidence has been captured.</p><button type="button" onClick={() => void capture()} disabled={working || connectionStatus !== "open"}>{working ? "Capturing..." : "Capture baseline parity"}</button></div> : null}
    {Object.keys(evidence).length ? <>
      <nav aria-label="Baseline parity evidence tabs">{sections.map((section) => <button type="button" key={section.id} aria-selected={active === section.id} onClick={() => setActive(section.id)}>{section.label}</button>)}</nav>
      {current ? <div className={styles.previewPanel}>
        <p className={styles.note}>Confidence: <strong>{label(current.confidence[active] ?? "unknown")}</strong> · parser {current.parser_version} · schema {current.schema_version}</p>
        {active === "failures" ? <ul className={styles.list}>{current.failures.length ? current.failures.map((failure) => <li key={failure.fingerprint}><code>{failure.fingerprint}</code><span>{failure.message}</span><strong>{failure.origin}</strong><small>{failure.count} occurrence(s) · {label(failure.severity)}</small></li>) : <li>No pre-existing baseline failures were fingerprinted.</li>}</ul> : null}
        {active === "routes" ? <pre className={styles.logViewer}>{JSON.stringify(current.routes, null, 2)}</pre> : null}
        {active === "backend-integration" ? <pre className={styles.logViewer}>{JSON.stringify(current.backend_integration, null, 2)}</pre> : null}
        {active === "anchors" ? <pre className={styles.logViewer}>{JSON.stringify(current.anchors, null, 2)}</pre> : null}
        <p className={styles.note}>State version {current.state_version} · event sequence {current.event_sequence} · {current.artifact_ids.length} immutable artifacts.</p>
      </div> : null}
    </> : null}
  </section>;
}
