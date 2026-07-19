"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { cancelStageTests, getStageTestLogs, getStageTests, startStageTests } from "@/api/stageTests";
import type { StageTestChange, StageTestSuite } from "@/types/stageTests";
import styles from "./ControlTowerShell.module.css";

type ConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";

const terminal = new Set(["passed", "failed", "blocked", "not_configured", "cancelled", "accepted_risk"]);
const suiteKindLabels: Record<string, string> = {
  unit: "Unit tests", integration: "Integration tests", e2e: "E2E tests", lint: "Lint",
};
const groupLabels: Record<string, string> = {
  baseline: "Baseline", new: "New test changes", resolved: "Resolved", not_configured: "Not configured",
};

function statusLabel(value: string) { return value.replaceAll("_", " "); }

export function StageTestPanel({
  runId, stageId, stateVersion, connectionStatus,
}: {
  runId: string; stageId: string; stateVersion: number; connectionStatus: ConnectionStatus;
}) {
  const [tests, setTests] = useState<{ test_id: string; status: string; suites: StageTestSuite[]; changes: StageTestChange[]; logs: string[]; artifact_ids: string[]; artifact_checksums: Record<string, string>; state_version: number; event_sequence: number; idempotent_replay: boolean; } | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [logs, setLogs] = useState<string[] | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const result = await getStageTests(runId, stageId);
      setTests(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setTests(null);
      } else {
        setError("Stage test evidence could not be loaded.");
      }
    } finally { setLoading(false); }
  }, [runId, stageId]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion]);
  useEffect(() => {
    if (tests?.status !== "running") return;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [refresh, tests?.status]);

  async function handleStart() {
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await startStageTests(runId, stageId, {
        expected_state_version: stateVersion,
        idempotency_key: `stage-tests-${runId}-${stageId}-${Date.now()}`,
        actor: "control-tower",
      });
      setTests(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The stage tests could not be started.");
    } finally { setWorking(false); }
  }

  async function handleCancel() {
    setWorking(true); setError(null);
    try { const result = await cancelStageTests(runId, stageId); setTests(result); }
    catch { setError("The test cancellation request could not be completed."); }
    finally { setWorking(false); }
  }

  async function handleViewLogs() {
    if (!tests) return;
    try {
      const result = await getStageTestLogs(runId, stageId, tests.test_id);
      setLogs(result.logs);
    } catch { setError("Logs could not be loaded."); }
  }

  const connectionLabel = useMemo(() => (
    connectionStatus === "open" ? "Live test suite state"
    : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..."
    : connectionStatus === "recovering" ? "Refreshing authoritative test state..."
    : connectionStatus === "failed" ? "Unable to refresh test state"
    : "Connecting to test events..."
  ), [connectionStatus]);

  const suitesByKind = useMemo(() => {
    if (!tests) return [];
    const map = new Map<string, StageTestSuite[]>();
    for (const s of tests.suites) {
      const list = map.get(s.kind) ?? [];
      list.push(s);
      map.set(s.kind, list);
    }
    return Array.from(map.entries());
  }, [tests]);

  const changesByGroup = useMemo(() => {
    if (!tests) return [];
    const map = new Map<string, StageTestChange[]>();
    for (const c of tests.changes) {
      const list = map.get(c.group) ?? [];
      list.push(c);
      map.set(c.group, list);
    }
    return Array.from(map.entries());
  }, [tests]);

  return (
    <section className={styles.panel} aria-labelledby="stage-test-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F12</p>
          <h2 id="stage-test-title">Stage test suite &amp; lint</h2>
          <p className={styles.note}>
            Run complete stage tests and conditional lint with baseline/new/resolved grouping.
          </p>
        </div>
        <span className={styles.status}>{tests ? statusLabel(tests.status) : "not loaded"}</span>
      </div>
      <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>

      {loading && <p role="status">Loading stage test state...</p>}
      {error && <p role="alert">{error}</p>}
      {stale && <p role="alert">The run state changed while tests were running. Refresh before retrying.</p>}

      {!loading && !tests && (
        <p className={styles.note}>No stage tests have been started yet.</p>
      )}

      {tests && (
        <>
          <div className={styles.previewPanel}>
            <div className={styles.previewHeader}>
              <h3>Test suites</h3>
              {tests.status === "running" ? (
                <button type="button" onClick={handleCancel} disabled={working}>
                  {working ? "Cancelling..." : "Cancel"}
                </button>
              ) : terminal.has(tests.status) ? (
                <button type="button" onClick={handleStart} disabled={working}>
                  {working ? "Starting..." : "Re-run"}
                </button>
              ) : (
                <button type="button" onClick={handleStart} disabled={working}>
                  {working ? "Starting..." : "Run tests"}
                </button>
              )}
            </div>

            {suitesByKind.length === 0 ? (
              <p className={styles.note}>No test suites configured.</p>
            ) : (
              <ul className={styles.list}>
                {suitesByKind.map(([kind, suites]) => (
                  <li key={kind}>
                    <strong>{suiteKindLabels[kind] ?? kind}</strong>
                    <ul>
                      {suites.map((suite) => (
                        <li key={suite.suite_id}>
                          <code>{suite.name}</code>
                          {suite.mandatory ? <strong className={styles.warning ?? ""}>Mandatory</strong> : <small>Optional</small>}
                          <strong>{statusLabel(suite.status)}</strong>
                          {suite.test_count != null && (
                            <small>
                              {suite.passed ?? 0}/{suite.test_count} passed
                              {suite.failed != null && suite.failed > 0 && <span className={styles.warning ?? ""}> · {suite.failed} failed</span>}
                              {suite.skipped != null && suite.skipped > 0 && <span> · {suite.skipped} skipped</span>}
                            </small>
                          )}
                          {suite.duration_ms != null && <small>{suite.duration_ms} ms</small>}
                          {suite.is_baseline && <small>Baseline</small>}
                          {suite.failed_tests.length > 0 && (
                            <ul>
                              {suite.failed_tests.map((t) => <li key={t} className={styles.warning ?? ""}><small>{t}</small></li>)}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {changesByGroup.length > 0 && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h3>Test changes</h3></div>
              <ul className={styles.list}>
                {changesByGroup.map(([group, changes]) => (
                  <li key={group}>
                    <strong>{groupLabels[group] ?? group}</strong>
                    <ul>
                      {changes.map((c) => (
                        <li key={c.test_id}>
                          <code>{c.name}</code>
                          <small>{c.suite_name}</small>
                          <strong>{statusLabel(c.current_status)}</strong>
                          {c.previous_status && <small>was {statusLabel(c.previous_status)}</small>}
                          {c.current_duration_ms != null && <small>{c.current_duration_ms} ms</small>}
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
              <h4>Evidence &amp; artifacts</h4>
              {tests.artifact_ids.length > 0 && (
                <button type="button" onClick={handleViewLogs}>
                  {logs ? "Refresh logs" : "View logs"}
                </button>
              )}
            </div>
            {tests.artifact_ids.length > 0 ? (
              <ul className={styles.list}>
                {tests.artifact_ids.map((id) => (
                  <li key={id}><code>{id}</code></li>
                ))}
              </ul>
            ) : (
              <p className={styles.note}>No artifacts recorded.</p>
            )}
            {logs && (
              <pre>{logs.length > 0 ? logs.join("\n").slice(0, 500) + (logs.join("\n").length > 500 ? "..." : "") : "(empty)"}</pre>
            )}
            <p className={styles.note}>
              state version {tests.state_version} · event sequence {tests.event_sequence}
              {tests.idempotent_replay ? " · idempotent replay" : ""}
            </p>
          </div>
        </>
      )}
    </section>
  );
}
