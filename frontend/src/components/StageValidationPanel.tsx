"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { cancelStageValidation, getStageValidation, getStageValidationLogs, startStageValidation } from "@/api/stageValidation";
import type { StageDiagnostic, StageValidationResponse, StageValidationStep } from "@/types/stageValidation";
import styles from "./ControlTowerShell.module.css";

type ConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";
type ValidationPhase = "idle" | "running" | "success" | "blocked" | "failed" | "stale";

const terminal = new Set(["passed", "failed", "blocked", "not_configured", "cancelled", "accepted_risk"]);
const stepKindLabels: Record<string, string> = { install: "Clean install", static: "Static checks" };
const severityIcon: Record<string, string> = { error: "✗", warning: "!", info: "i" };

function statusLabel(value: string) { return value.replaceAll("_", " "); }

function severityClass(severity: string): string {
  return severity === "error" ? styles.error ?? "error" : severity === "warning" ? styles.warning ?? "warning" : styles.info ?? "info";
}

export function StageValidationPanel({
  runId, stageId, stateVersion, connectionStatus,
}: {
  runId: string; stageId: string; stateVersion: number; connectionStatus: ConnectionStatus;
}) {
  const [validation, setValidation] = useState<StageValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [logs, setLogs] = useState<string[] | null>(null);
  const [showLogs, setShowLogs] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const result = await getStageValidation(runId, stageId);
      setValidation(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setValidation(null);
      } else {
        setError("Stage validation evidence could not be loaded.");
      }
    } finally { setLoading(false); }
  }, [runId, stageId]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion]);
  useEffect(() => {
    if (validation?.status !== "running") return;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [refresh, validation?.status]);

  async function handleStart() {
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await startStageValidation(runId, stageId, {
        expected_state_version: stateVersion,
        idempotency_key: `stage-validation-${runId}-${stageId}-${Date.now()}`,
        actor: "control-tower",
      });
      setValidation(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The stage validation could not be started.");
    } finally { setWorking(false); }
  }

  async function handleCancel() {
    setWorking(true); setError(null);
    try { const result = await cancelStageValidation(runId, stageId); setValidation(result); }
    catch { setError("The cancellation request could not be completed."); }
    finally { setWorking(false); }
  }

  async function handleViewLogs() {
    if (!validation) return;
    try {
      const result = await getStageValidationLogs(runId, stageId, validation.validation_id);
      setLogs(result.logs);
      setShowLogs(true);
    } catch { setError("Logs could not be loaded."); }
  }

  const phase: ValidationPhase = loading ? "idle" : error ? "failed" : stale ? "stale" : !validation ? "idle" : validation.status === "running" ? "running" : terminal.has(validation.status) ? validation.status as ValidationPhase : "blocked";

  const connectionLabel = useMemo(() => (
    connectionStatus === "open" ? "Live stage validation state"
    : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..."
    : connectionStatus === "recovering" ? "Refreshing authoritative validation state..."
    : connectionStatus === "failed" ? "Unable to refresh validation state"
    : "Connecting to validation events..."
  ), [connectionStatus]);

  const stepsByKind = useMemo(() => {
    if (!validation) return [];
    const map = new Map<string, StageValidationStep[]>();
    for (const step of validation.steps) {
      const list = map.get(step.kind) ?? [];
      list.push(step);
      map.set(step.kind, list);
    }
    return Array.from(map.entries());
  }, [validation]);

  const diagnosticsByFile = useMemo(() => {
    if (!validation) return new Map<string | "__ungrouped__", StageDiagnostic[]>();
    const map = new Map<string | "__ungrouped__", StageDiagnostic[]>();
    for (const d of validation.diagnostics) {
      const key = d.file ?? "__ungrouped__";
      const list = map.get(key) ?? [];
      list.push(d);
      map.set(key, list);
    }
    return map;
  }, [validation]);

  return (
    <section className={styles.panel} aria-labelledby="stage-validation-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F10</p>
          <h2 id="stage-validation-title">Stage validation — final install &amp; static checks</h2>
          <p className={styles.note}>
            Run a clean final dependency install and inspect TypeScript/template/import diagnostics.
          </p>
        </div>
        <span className={styles.status}>{validation ? statusLabel(validation.status) : "not loaded"}</span>
      </div>
      <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>

      {loading && <p role="status">Loading stage validation state...</p>}
      {error && <p role="alert">{error}</p>}
      {stale && <p role="alert">The run state changed while validation was requested. Refresh before retrying.</p>}

      {!loading && !validation && (
        <p className={styles.note}>No stage validation has been started yet.</p>
      )}

      {validation && (
        <>
          <div className={styles.previewPanel}>
            <div className={styles.previewHeader}>
              <h3>Step timeline</h3>
              {validation.status === "running" ? (
                <button type="button" onClick={handleCancel} disabled={working}>
                  {working ? "Cancelling..." : "Cancel"}
                </button>
              ) : terminal.has(validation.status) ? (
                <button type="button" onClick={handleStart} disabled={working}>
                  {working ? "Starting..." : "Re-run"}
                </button>
              ) : (
                <button type="button" onClick={handleStart} disabled={working}>
                  {working ? "Starting..." : "Run validation"}
                </button>
              )}
            </div>
            {stepsByKind.length === 0 ? (
              <p className={styles.note}>No steps recorded.</p>
            ) : (
              <ul className={styles.list}>
                {stepsByKind.map(([kind, steps]) => (
                  <li key={kind}>
                    <strong>{stepKindLabels[kind] ?? kind}</strong>
                    <ul>
                      {steps.map((step) => (
                        <li key={step.step_id}>
                          <code>{step.name}</code>
                          <strong>{statusLabel(step.status)}</strong>
                          {step.duration_ms != null && <small>{step.duration_ms} ms</small>}
                          {step.detail && <small>{step.detail}</small>}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {diagnosticsByFile.size > 0 && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h3>Diagnostics ({validation.diagnostics.length})</h3></div>
              <ul className={styles.list}>
                {Array.from(diagnosticsByFile.entries()).map(([file, diags]) => (
                  <li key={file}>
                    <code>{file === "__ungrouped__" ? "(no file)" : file}</code>
                    <ul>
                      {diags.map((d) => (
                        <li key={d.diagnostic_id} className={severityClass(d.severity)}>
                          <span>{severityIcon[d.severity] ?? "?"}</span>
                          <code>{d.code}</code>
                          <span>{d.message}</span>
                          {(d.line != null || d.column != null) && (
                            <small>{d.line != null ? `:${d.line}` : ""}{d.column != null ? `:${d.column}` : ""}</small>
                          )}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className={styles.previewPanel}>
            <div className={styles.previewHeader}>
              <h4>Artifacts &amp; evidence</h4>
              {validation.artifact_ids.length > 0 && (
                <button type="button" onClick={handleViewLogs} disabled={showLogs}>
                  {showLogs ? "Logs shown" : "Show logs"}
                </button>
              )}
            </div>
            {validation.artifact_ids.length > 0 ? (
              <ul className={styles.list}>
                {validation.artifact_ids.map((id) => (
                  <li key={id}><code>{id}</code></li>
                ))}
              </ul>
            ) : (
              <p className={styles.note}>No artifacts recorded.</p>
            )}
            <p className={styles.note}>
              state version {validation.state_version} · event sequence {validation.event_sequence}
              {validation.idempotent_replay ? " · idempotent replay" : ""}
            </p>
          </div>

          {showLogs && logs && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h4>Logs</h4></div>
              <pre>{logs.length > 0 ? logs.join("\n") : "(empty)"}</pre>
            </div>
          )}
        </>
      )}
    </section>
  );
}
