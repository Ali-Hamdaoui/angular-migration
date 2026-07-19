"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getStageAssurance, submitG09Decision, updateStageAssurance } from "@/api/stageAssurance";
import type { AssuranceGate, AssuranceCard, AssuranceManualItem, AssuranceDecision, ApiDelta, RouteDelta } from "@/types/stageAssurance";
import styles from "./ControlTowerShell.module.css";

type ConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";

const gateNameLabels: Record<string, string> = {
  install_static: "Install & static", build_matrix: "Build matrix", test_suite: "Test suite",
  parity_evidence: "Parity evidence", security_scan: "Security scan", quality_gate: "Quality gate",
};
const gateEmojis: Record<string, string> = {
  passed: "✓", failed: "✗", conditional: "~", manual_required: "!", deferred: "⏳",
  not_evaluated: "?", accepted_risk: "⚠",
};

function statusLabel(value: string) { return value.replaceAll("_", " "); }

export function StageAssurancePanel({
  runId, stageId, stateVersion, connectionStatus,
}: {
  runId: string; stageId: string; stateVersion: number; connectionStatus: ConnectionStatus;
}) {
  const [assurance, setAssurance] = useState<{
    assurance_id: string; status: string; gates: AssuranceGate[]; route_deltas: RouteDelta[];
    api_deltas: ApiDelta[]; cards: AssuranceCard[]; manual_items: AssuranceManualItem[];
    artifact_ids: string[]; artifact_checksums: Record<string, string>; g09_decision: AssuranceDecision | null;
    state_version: number; event_sequence: number; idempotent_replay: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [g09Decision, setG09Decision] = useState<AssuranceDecision>("PENDING");
  const [g09Rationale, setG09Rationale] = useState("");
  const [decisionSubmitted, setDecisionSubmitted] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const result = await getStageAssurance(runId, stageId);
      setAssurance(result);
      if (result.g09_decision && result.g09_decision !== "PENDING") {
        setDecisionSubmitted(true);
        setG09Decision(result.g09_decision);
      }
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setAssurance(null);
      } else {
        setError("Stage assurance data could not be loaded.");
      }
    } finally { setLoading(false); }
  }, [runId, stageId]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion]);
  useEffect(() => {
    if (assurance?.status !== "running") return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [refresh, assurance?.status]);

  async function handleStartAssurance() {
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await updateStageAssurance(runId, stageId, {
        expected_state_version: stateVersion,
        idempotency_key: `stage-assurance-${runId}-${stageId}-${Date.now()}`,
        actor: "control-tower",
      });
      setAssurance(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The assurance evaluation could not be started.");
    } finally { setWorking(false); }
  }

  async function handleG09Submit() {
    if (g09Decision === "PENDING") return;
    setWorking(true); setError(null);
    try {
      const result = await submitG09Decision(runId, stageId, {
        expected_state_version: stateVersion,
        idempotency_key: `g09-decision-${runId}-${stageId}-${Date.now()}`,
        actor: "control-tower",
        decision: g09Decision,
        rationale: g09Rationale || undefined,
      });
      setAssurance(result);
      setDecisionSubmitted(true);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The G09 decision could not be submitted.");
    } finally { setWorking(false); }
  }

  const connectionLabel = useMemo(() => (
    connectionStatus === "open" ? "Live assurance state"
    : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..."
    : connectionStatus === "recovering" ? "Refreshing authoritative assurance state..."
    : connectionStatus === "failed" ? "Unable to refresh assurance state"
    : "Connecting to assurance events..."
  ), [connectionStatus]);

  return (
    <section className={styles.panel} aria-labelledby="stage-assurance-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F13</p>
          <h2 id="stage-assurance-title">Stage assurance review — G09</h2>
          <p className={styles.note}>
            Compare parity evidence, review gates, and decide G09 validation acceptance.
          </p>
        </div>
        <span className={styles.status}>{assurance ? statusLabel(assurance.status) : "not loaded"}</span>
      </div>
      <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>

      {loading && <p role="status">Loading assurance data...</p>}
      {error && <p role="alert">{error}</p>}
      {stale && <p role="alert">The run state changed while assurance was loading. Refresh before retrying.</p>}

      {!loading && !assurance && (
        <p className={styles.note}>No assurance evaluation has been started.</p>
      )}

      {assurance && (
        <>
          {/* Gate matrix */}
          <div className={styles.previewPanel}>
            <div className={styles.previewHeader}>
              <h3>Gate matrix</h3>
              {assurance.status !== "running" ? (
                <button type="button" onClick={handleStartAssurance} disabled={working}>
                  {working ? "Starting..." : assurance.status === "passed" || assurance.status === "failed" || assurance.status === "passed_with_manual_items" ? "Re-evaluate" : "Evaluate assurance"}
                </button>
              ) : null}
            </div>
            <ul className={styles.list}>
              {assurance.gates.map((gate) => (
                <li key={gate.gate_id}>
                  <span>{gateEmojis[gate.status] ?? "?"}</span>
                  <strong>{gateNameLabels[gate.name] ?? gate.label}</strong>
                  <strong>{statusLabel(gate.status)}</strong>
                  {gate.detail && <small>{gate.detail}</small>}
                  {gate.artifact_ids.length > 0 && <small>{gate.artifact_ids.length} artifacts</small>}
                </li>
              ))}
            </ul>
          </div>

          {/* Route & API deltas */}
          {(assurance.route_deltas.length > 0 || assurance.api_deltas.length > 0) && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h3>Route &amp; API deltas</h3></div>
              {assurance.route_deltas.length > 0 && (
                <>
                  <h4>Route changes</h4>
                  <ul className={styles.list}>
                    {assurance.route_deltas.map((d) => (
                      <li key={`route-${d.route}`}>
                        <code>{d.route}</code>
                        <strong>{d.type}</strong>
                        {d.previous_controller && <small>was {d.previous_controller}</small>}
                        {d.current_controller && <small>now {d.current_controller}</small>}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {assurance.api_deltas.length > 0 && (
                <>
                  <h4>API changes</h4>
                  <ul className={styles.list}>
                    {assurance.api_deltas.map((d) => (
                      <li key={`api-${d.endpoint}-${d.method}`}>
                        <code>{d.method} {d.endpoint}</code>
                        <strong>{d.type}</strong>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}

          {/* Assurance cards */}
          {assurance.cards.length > 0 && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h3>Independent assurance</h3></div>
              <ul className={styles.list}>
                {assurance.cards.map((card) => (
                  <li key={card.card_id}>
                    <span>{gateEmojis[card.status] ?? "?"}</span>
                    <strong>{card.title}</strong>
                    <small>{card.summary}</small>
                    <strong>{card.proof_label.replace("_", " ")}</strong>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Manual / deferred items */}
          {assurance.manual_items.length > 0 && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h3>Manual &amp; deferred items</h3></div>
              <ul className={styles.list}>
                {assurance.manual_items.map((item) => (
                  <li key={item.item_id}>
                    <strong>{item.required ? "Required" : "Optional"}</strong>
                    <span>{item.description}</span>
                    {item.completed ? <small>Completed by {item.completed_by}</small> : <small>Pending</small>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* G09 controls */}
          <div className={styles.previewPanel}>
            <div className={styles.previewHeader}><h3>G09 validation decision</h3></div>
            {decisionSubmitted ? (
              <p className={styles.note}>Decision submitted: {statusLabel(g09Decision)}</p>
            ) : (
              <div>
                <label htmlFor="g09-decision">Decision:</label>
                <select id="g09-decision" value={g09Decision} onChange={(e) => setG09Decision(e.target.value as AssuranceDecision)}>
                  <option value="PENDING">— Select —</option>
                  <option value="ACCEPT_ALL">Accept all</option>
                  <option value="ACCEPT_WITH_RISK">Accept with risk</option>
                  <option value="REJECT">Reject</option>
                  <option value="MODIFICATION_REQUESTED">Modification requested</option>
                </select>
                <label htmlFor="g09-rationale">Rationale:</label>
                <input id="g09-rationale" type="text" value={g09Rationale} onChange={(e) => setG09Rationale(e.target.value)} placeholder="Optional rationale" />
                <button type="button" onClick={handleG09Submit} disabled={working || g09Decision === "PENDING"}>
                  {working ? "Submitting..." : "Submit decision"}
                </button>
              </div>
            )}
          </div>

          <p className={styles.note}>
            state version {assurance.state_version} · event sequence {assurance.event_sequence}
            {assurance.idempotent_replay ? " · idempotent replay" : ""}
          </p>
        </>
      )}
    </section>
  );
}
