"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { cancelMigration } from "@/api/migrations";
import { getBaseline, getBaselineCommand, installBaseline } from "@/api/baseline";
import { getExecutionProfiles } from "@/api/executionProfiles";
import type { AuthoritativeRunStateDto, BaselineInstallResponse, BaselineResponse, ExecutionProfileResponse } from "@/types/generated/api";
import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import styles from "./ControlTowerShell.module.css";

const TERMINAL = new Set(["SUCCEEDED", "FAILED", "REJECTED", "TIMED_OUT", "CANCELLED"]);

function key(runId: string) { return `baseline-install-${runId}-${Date.now()}`; }
function eventExecutionId(state: AuthoritativeRunStateDto) {
  const event = [...state.workflow_events].reverse().find((item) => ["COMMAND_QUEUED", "COMMAND_STARTED", "COMMAND_OUTPUT_AVAILABLE", "BASELINE_INSTALL_SUCCEEDED", "BASELINE_INSTALL_FAILED", "COMMAND_CANCELLED", "COMMAND_INTERRUPTED"].includes(item.event_type));
  const value = event?.payload.execution_id;
  return typeof value === "string" ? value : null;
}

export function BaselineInstallationPanel({ runId, initialState, connectionStatus }: { runId: string; initialState: AuthoritativeRunStateDto; connectionStatus: AuthoritativeConnectionStatus }) {
  const [baseline, setBaseline] = useState<BaselineResponse | null>(null);
  const [profile, setProfile] = useState<ExecutionProfileResponse | null>(null);
  const [installation, setInstallation] = useState<BaselineInstallResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(() => eventExecutionId(initialState));

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [nextBaseline, nextProfile] = await Promise.all([getBaseline(runId), getExecutionProfiles(runId)]);
      setBaseline(nextBaseline); setProfile(nextProfile);
      setExecutionId((current) => current ?? eventExecutionId(initialState));
    } catch (reason: unknown) {
      if (!(reason instanceof ApiClientError && reason.status === 404)) setError("Baseline installation evidence could not be loaded.");
    } finally { setLoading(false); }
  }, [runId, initialState]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const discovered = eventExecutionId(initialState);
    if (discovered) setExecutionId(discovered);
  }, [initialState]);
  useEffect(() => {
    if (!executionId || (installation && TERMINAL.has(installation.status))) return;
    const timer = window.setInterval(() => { void getBaselineCommand(runId, executionId).then(setInstallation).catch(() => undefined); }, 3000);
    return () => window.clearInterval(timer);
  }, [executionId, installation, runId]);

  async function start() {
    const selected = profile?.selected_profile;
    if (!selected) return;
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await installBaseline(runId, { expected_state_version: initialState.state_version, idempotency_key: key(runId), actor: "control-tower", runtime_profile_id: selected.profile_id, runtime_checksum: selected.checksum });
      setInstallation(result); setExecutionId(result.execution_id);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The frozen baseline installation could not be started.");
    } finally { setWorking(false); }
  }

  async function cancel() {
    setWorking(true); setError(null);
    try { await cancelMigration(runId); if (executionId) setInstallation(await getBaselineCommand(runId, executionId)); }
    catch { setError("The installation cancellation request could not be completed."); }
    finally { setWorking(false); }
  }

  const status = installation?.status ?? (baseline?.blockers.length ? "BLOCKED" : "NOT_STARTED");
  const selected = profile?.selected_profile;
  const blocked = Boolean(baseline?.blockers.length) || baseline?.authorization_status !== "authorized" || profile?.status === "blocked" || !selected;
  const statusText = useMemo(() => status.replaceAll("_", " ").toLowerCase(), [status]);
  return <section className={styles.panel} aria-labelledby="baseline-installation-title">
    <div className={styles.header}><div><p className={styles.kicker}>S1-F11-I03</p><h2 id="baseline-installation-title">Frozen baseline clean installation</h2><p className={styles.note}>Runs the registered <code>npm ci</code> command in the authorized baseline sandbox and inspects immutable evidence.</p></div><span className={styles.status}>{statusText}</span></div>
    {loading ? <p role="status">Loading installation prerequisites...</p> : null}
    <div className={styles.connectionBar} role="status" aria-live="polite">{connectionStatus === "open" ? "Live installation events" : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..." : connectionStatus === "recovering" ? "Refreshing authoritative installation state..." : connectionStatus === "failed" ? "Unable to refresh installation state" : "Connecting to installation events..."}</div>
    {error ? <p role="alert">{error}</p> : null}
    {stale ? <p role="alert">The run changed while installation was requested. Refresh the authoritative state before retrying.</p> : null}
    {!loading && !baseline ? <p className={styles.note}>No baseline qualification exists yet.</p> : null}
    {baseline?.blockers.length ? <div role="alert"><h3>Blocked</h3><ul>{baseline.blockers.map((item) => <li key={item}><code>{item}</code></li>)}</ul></div> : null}
    {profile?.status === "blocked" ? <p role="alert">No compatible approved runtime profile is available.</p> : null}
    {installation ? <><dl className={styles.metadataGrid}><div><dt>Command</dt><dd><code>npm ci</code></dd></div><div><dt>Execution</dt><dd><code>{installation.execution_id}</code></dd></div><div><dt>Exit code</dt><dd>{installation.exit_code ?? "pending"}</dd></div><div><dt>Duration</dt><dd>{installation.duration_ms == null ? "pending" : `${installation.duration_ms} ms`}</dd></div></dl>{installation.blockers.length ? <ul>{installation.blockers.map((item) => <li key={item}><code>{item}</code></li>)}</ul> : null}<p className={styles.note}>Event sequence {installation.event_sequence}; state version {installation.state_version}. Artifacts: {installation.artifact_ids.length}.</p>{installation.reconstruction_required ? <p role="alert">The workspace requires reconstruction before it can be reused.</p> : null}</> : <p className={styles.note}>No installation has been requested.</p>}
    <div className={styles.row}><span>Runtime {selected ? `${selected.profile_id} (${selected.checksum})` : "selection required"}</span><span>{installation && !TERMINAL.has(installation.status) ? <button type="button" disabled={working} onClick={cancel}>Cancel installation</button> : <button type="button" disabled={working || blocked} onClick={start}>{working ? "Starting..." : "Install frozen baseline"}</button>}</span></div>
  </section>;
}