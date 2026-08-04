"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
function confidenceKey(section: Section): string { return section === "backend-integration" ? "backend_integration" : section; }

export function BaselineParityPanel({ runId, stateVersion, connectionStatus, workflowEvents = [] }: { runId: string; stateVersion: number; connectionStatus: ConnectionStatus; workflowEvents?: Array<{ event_type: string }> }) {
  const [evidence, setEvidence] = useState<Partial<Record<Section, BaselineParityResponse>>>({});
  const [active, setActive] = useState<Section>("failures");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [sectionErrors, setSectionErrors] = useState<Partial<Record<Section, string>>>({});
  const refreshing = useRef(false);

  const refresh = useCallback(async (force = false) => {
    if (refreshing.current && !force) return;
    refreshing.current = true;
    setLoading(true); setError(null); setSectionErrors({});
    const results = await Promise.allSettled(sections.map(({ id }) => getBaselineParitySection(runId, id)));
    const nextEvidence: Partial<Record<Section, BaselineParityResponse>> = {};
    const nextErrors: Partial<Record<Section, string>> = {};
    results.forEach((result, index) => {
      const section = sections[index].id;
      if (result.status === "fulfilled") nextEvidence[section] = result.value;
      else if (!(result.reason instanceof ApiClientError && result.reason.status === 404)) nextErrors[section] = "The backend could not load this parity section.";
    });
    setEvidence(nextEvidence);
    setSectionErrors(nextErrors);
    setLoading(false);
    refreshing.current = false;
  }, [runId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh(); }, 50);
    return () => window.clearTimeout(timer);
  }, [refresh, stateVersion]);

  async function capture() {
    setWorking(true); setError(null); setStale(false);
    try { await captureBaselineParity(runId, { expected_state_version: stateVersion, idempotency_key: operationKey(runId), actor: "control-tower" }); await refresh(true); }
    catch (reason: unknown) { if (reason instanceof ApiClientError && reason.status === 409) setStale(true); else setError("Baseline parity evidence could not be captured."); }
    finally { setWorking(false); }
  }

  const current = evidence[active];
  const hasG03 = workflowEvents.some((event) => event.event_type === "G03_CREATED" || event.event_type === "G03_APPROVED");
  const validationComplete = workflowEvents.some((event) => ["BASELINE_BUILD_COMPLETED", "BASELINE_TESTS_COMPLETED", "BASELINE_LINT_COMPLETED"].includes(event.event_type));
  const captured = Object.keys(evidence).length > 0;
  const connectionLabel = connectionStatus === "open" ? "Live baseline parity state" : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..." : connectionStatus === "recovering" ? "Refreshing authoritative parity state..." : connectionStatus === "failed" ? "Unable to refresh parity state" : "Connecting to parity evidence...";
  return <section className={styles.panel} aria-labelledby="baseline-parity-title">
    <div className={styles.header}><div><p className={styles.kicker}>Baseline reference</p><h2 id="baseline-parity-title">Baseline reference</h2><p className={styles.note}>Structural evidence and known baseline failures; this is not a functional parity conclusion.</p></div><span className={styles.status}>{working ? "capturing" : captured ? (current?.failures.length ? "captured with known baseline failures" : "captured") : hasG03 ? "integrity error" : validationComplete ? "ready to capture" : "waiting for baseline validation"}</span></div>
    <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>
    {loading ? <p role="status">Loading baseline parity evidence...</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {Object.entries(sectionErrors).map(([section, message]) => <p role="alert" key={section}>{section}: {message}</p>)}
    {stale ? <p role="alert">The run changed while parity evidence was requested. Refresh the authoritative state before retrying.</p> : null}
    {!loading && !captured && hasG03 ? <div className={styles.previewPanel}><p role="alert">Required baseline reference evidence is missing. The current G03 package is not valid for approval.</p><p className={styles.note}>Capture new parity evidence through backend requalification before continuing.</p></div> : null}
    {!loading && !captured && !hasG03 ? <div className={styles.previewPanel}><p className={styles.note}>{validationComplete ? "Baseline validation is complete; parity capture is ready." : "Waiting for baseline validation."}</p><button type="button" onClick={() => void capture()} disabled={working || connectionStatus !== "open" || !validationComplete}>{working ? "Capturing..." : "Capture baseline parity"}</button></div> : null}
    {captured ? <>
      <nav aria-label="Baseline parity evidence tabs">{sections.map((section) => <button type="button" key={section.id} aria-selected={active === section.id} onClick={() => setActive(section.id)}>{section.label}</button>)}</nav>
      {current ? <div className={styles.previewPanel}>
        <p className={styles.note}>Confidence: <strong>{label(current.confidence[confidenceKey(active)] ?? "unknown")}</strong> · parser {current.parser_version} · schema {current.schema_version}</p>
        {active === "failures" ? <ul className={styles.list}>{current.failures.length ? current.failures.map((failure) => <li key={failure.fingerprint}><code>{failure.fingerprint}</code><span>{failure.message}</span><strong>{failure.origin}</strong><small>{failure.count} occurrence(s) · {label(failure.severity)}</small></li>) : <li>No pre-existing baseline failures were fingerprinted.</li>}</ul> : null}
        {active === "routes" ? <pre className={styles.logViewer}>{JSON.stringify(current.routes, null, 2)}</pre> : null}
        {active === "backend-integration" ? <pre className={styles.logViewer}>{JSON.stringify(current.backend_integration, null, 2)}</pre> : null}
        {active === "anchors" ? <pre className={styles.logViewer}>{JSON.stringify(current.anchors, null, 2)}</pre> : null}
        <p className={styles.note}>State version {current.state_version} · event sequence {current.event_sequence} · {current.artifact_ids.length} immutable artifacts.</p>
      </div> : null}
    </> : null}
  </section>;
}
