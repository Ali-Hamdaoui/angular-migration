"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { cancelBaseline, getBaseline, getBaselineCommand, installBaseline } from "@/api/baseline";
import { getExecutionProfiles } from "@/api/executionProfiles";
import type { AuthoritativeRunStateDto, BaselineInstallResponse, BaselineResponse, ExecutionProfileResponse } from "@/types/generated/api";
import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import styles from "./ControlTowerShell.module.css";

const TERMINAL = new Set(["SUCCEEDED", "FAILED", "REJECTED", "TIMED_OUT", "CANCELLED"]);
const REQUIRED_INSTALLATION_FIELDS = ["run_id", "execution_id", "command_id", "status", "state_version", "event_sequence"] as const;

function key(runId: string) { return `baseline-install-${runId}-${Date.now()}`; }
function isTerminal(status: string) { return TERMINAL.has(status.toUpperCase()); }
function eventExecutionId(state: AuthoritativeRunStateDto) {
  const event = [...state.workflow_events].reverse().find((item) => item.stage_id === null && ["COMMAND_QUEUED", "COMMAND_STARTED", "COMMAND_OUTPUT_AVAILABLE", "BASELINE_INSTALL_SUCCEEDED", "BASELINE_INSTALL_FAILED", "COMMAND_CANCELLED", "COMMAND_INTERRUPTED"].includes(item.event_type));
  const value = event?.payload.execution_id;
  return typeof value === "string" ? value : null;
}
function missingInstallationFields(value: BaselineInstallResponse | null) {
  return value ? REQUIRED_INSTALLATION_FIELDS.filter((field) => value[field] == null) : [];
}

export function BaselineInstallationPanel({ runId, initialState, connectionStatus, refreshAuthoritativeState }: { runId: string; initialState: AuthoritativeRunStateDto; connectionStatus: AuthoritativeConnectionStatus; refreshAuthoritativeState?: () => Promise<void> | void }) {
  const [baseline, setBaseline] = useState<BaselineResponse | null>(null);
  const [profile, setProfile] = useState<ExecutionProfileResponse | null>(null);
  const [installation, setInstallation] = useState<BaselineInstallResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [output, setOutput] = useState<string[]>([]);
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
    const chunks = initialState.workflow_events
      .filter((event) => event.stage_id === null && event.event_type === "COMMAND_OUTPUT_CHUNK")
      .map((event) => event.payload)
      .filter((payload): payload is Record<string, unknown> => typeof payload === "object" && payload !== null && typeof payload.chunk === "string")
      .map((payload) => payload.chunk as string);
    if (chunks.length) setOutput(chunks);
  }, [initialState]);
  useEffect(() => {
    if (!executionId || (installation?.status && isTerminal(installation.status))) return;
    const timer = window.setInterval(() => { void getBaselineCommand(runId, executionId).then(setInstallation).catch(() => undefined); }, 3000);
    return () => window.clearInterval(timer);
  }, [executionId, installation, runId]);
  useEffect(() => {
    if (!installation || !installation.status || isTerminal(installation.status) || !installation.started_at) return;
    const timer = window.setInterval(() => setElapsed(Math.max(0, Date.now() - Date.parse(installation.started_at!))), 250);
    return () => window.clearInterval(timer);
  }, [installation]);

  async function start() {
    const selected = profile?.selected_profile;
    if (!selected) return;
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await installBaseline(runId, { expected_state_version: initialState.state_version, idempotency_key: key(runId), actor: "control-tower", runtime_profile_id: selected.profile_id, runtime_checksum: selected.checksum });
      setInstallation(result); setExecutionId(result.execution_id);
      await refreshAuthoritativeState?.();
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The frozen baseline installation could not be started.");
    } finally { setWorking(false); }
  }

  async function cancel() {
    setWorking(true); setError(null);
    try {
      if (executionId) {
        setInstallation(await cancelBaseline(runId, executionId, { expected_state_version: initialState.state_version, idempotency_key: `baseline-cancel-${runId}-${executionId}`, actor: "control-tower" }));
        await refreshAuthoritativeState?.();
      }
    }
    catch { setError("The installation cancellation request could not be completed."); }
    finally { setWorking(false); }
  }

  const baselineBlockers = Array.isArray(baseline?.blockers) ? baseline.blockers : [];
  const installationBlockers = Array.isArray(installation?.blockers) ? installation.blockers : [];
  const artifactIds = Array.isArray(installation?.artifact_ids) ? installation.artifact_ids : [];
  const missingFields = missingInstallationFields(installation);
  const status = installation?.status ?? (baselineBlockers.length ? "BLOCKED" : "NOT_STARTED");
  const selected = profile?.selected_profile;
  const blocked = Boolean(baselineBlockers.length) || baseline?.authorization_status !== "authorized" || profile?.status === "blocked" || !selected;
  const statusText = useMemo(() => status.replaceAll("_", " ").toLowerCase(), [status]);
  return <section className={styles.panel} aria-labelledby="baseline-installation-title">
    <div className={styles.header}><div><p className={styles.kicker}>Install baseline dependencies</p><h2 id="baseline-installation-title">Install baseline dependencies</h2><p className={styles.note}>Runs the registered <code>npm ci</code> command in the authorized baseline sandbox and inspects immutable evidence.</p></div><span className={styles.status}>{statusText}</span></div>
    {loading ? <p role="status">Loading installation prerequisites...</p> : null}
    <div className={styles.connectionBar} role="status" aria-live="polite">{connectionStatus === "open" ? "Live installation events" : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..." : connectionStatus === "recovering" ? "Refreshing authoritative installation state..." : connectionStatus === "failed" ? "Unable to refresh installation state" : "Connecting to installation events..."}</div>
    {error ? <p role="alert">{error}</p> : null}
    {stale ? <p role="alert">The run changed while installation was requested. Refresh the authoritative state before retrying.</p> : null}
    {!loading && !baseline ? <p className={styles.note}>No baseline qualification exists yet.</p> : null}
    {baselineBlockers.length ? <div role="alert"><h3>Blocked</h3><ul>{baselineBlockers.map((item) => <li key={item}><code>{item}</code></li>)}</ul></div> : null}
    {profile?.status === "blocked" ? <p role="alert">No compatible approved runtime profile is available.</p> : null}
    {missingFields.length ? <p role="alert">Installation projection incomplete. Missing required fields: <code>{missingFields.join(", ")}</code>.</p> : null}
    {installation ? <><dl className={styles.metadataGrid}><div><dt>Command</dt><dd><code>npm ci</code></dd></div><div><dt>Execution</dt><dd><code>{installation.execution_id ?? "unavailable"}</code></dd></div><div><dt>Exit code</dt><dd>{installation.exit_code ?? "pending"}</dd></div><div><dt>Duration</dt><dd>{installation.duration_ms == null ? "pending" : `${installation.duration_ms} ms`}</dd></div></dl>{installationBlockers.length ? <><p role="alert">Failure class: {installationBlockers.some((item) => item.includes("ENVIRONMENT") || item.includes("PROCESS")) ? "environment" : "project or workspace"}</p><ul>{installationBlockers.map((item) => <li key={item}><code>{item}</code></li>)}</ul></> : null}<p className={styles.note}>Event sequence {installation.event_sequence ?? "unavailable"}; state version {installation.state_version ?? "unavailable"}. Elapsed: {Math.round((elapsed || installation.duration_ms || 0) / 1000)}s.</p><pre className={styles.logViewer} aria-label="Baseline installation live logs">{output.length ? output.join("") : "Waiting for command output..."}</pre><ul className={styles.list}>{artifactIds.map((id) => <li key={id}><a className={styles.actionLink} href={`${process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000"}/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">Artifact {id}</a></li>)}</ul>{installation.reconstruction_required ? <p role="alert">The workspace requires reconstruction before it can be reused.</p> : null}</> : <p className={styles.note}>No installation has been requested.</p>}
    <div className={styles.row}><span>Runtime {selected ? `${selected.profile_id} (${selected.checksum})` : "selection required"}</span><span>{installation?.status && !isTerminal(installation.status) ? <button type="button" disabled={working} onClick={cancel}>Cancel installation</button> : <button type="button" disabled={working || blocked} onClick={start}>{working ? "Starting..." : "Install frozen baseline"}</button>}</span></div>
  </section>;
}
