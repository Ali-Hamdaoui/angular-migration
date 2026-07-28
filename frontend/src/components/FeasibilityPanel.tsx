"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import { decideG05, getFeasibility, queueFeasibilityResolution } from "@/api/compatibility";
import type { FeasibilityResponse, G05Decision } from "@/types/compatibility";
import type { ArtifactRefDto, AuthoritativeRunStateDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

const decisions: Array<{ value: G05Decision; label: string }> = [
  { value: "approve", label: "Approve G05" },
  { value: "approve_with_comment", label: "Approve with comment" },
  { value: "request_modification", label: "Request modification" },
  { value: "reject", label: "Reject G05" },
];
const F05_EVENTS = ["COMPATIBILITY_RESOLUTION_STARTED", "COMPATIBILITY_RESOLUTION_COMPLETED", "COMPATIBILITY_RESOLUTION_BLOCKED", "G05_CREATED", "G05_APPROVED", "G05_MODIFICATION_REQUESTED", "G05_REJECTED", "G05_STALE"];

function correlationFrom(error: ApiClientError) {
  try { return (JSON.parse(error.responseBody ?? "{}") as { correlation_id?: string }).correlation_id ?? "unavailable"; } catch { return "unavailable"; }
}

function operationKey(prefix: string, runId: string) { return `${prefix}-${runId}`; }

type Feature5Inputs = AuthoritativeRunStateDto & { source_angular_exact?: string | null; runtime_candidates?: Array<Record<string, unknown>>; registry_snapshot?: { snapshot_id?: string; checksum?: string } | null; catalogue_version?: string | null };
function sourceVersion(state: AuthoritativeRunStateDto) { return (state as Feature5Inputs).source_angular_exact ?? null; }

export function FeasibilityPanel({ runId, initialState, connectionStatus, workflowEvents, refreshAuthoritativeState }: { runId: string; initialState: AuthoritativeRunStateDto; connectionStatus: string; artifacts: ArtifactRefDto[]; workflowEvents: Array<{ event_type: string; sequence: number }>; refreshAuthoritativeState?: () => Promise<unknown> }) {
  const [feasibility, setFeasibility] = useState<FeasibilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [decision, setDecision] = useState<G05Decision>("approve");
  const [comment, setComment] = useState("");
  const operationKeys = useRef(new Map<string, string>());
  const stableOperationKey = (prefix: string) => {
    const key = operationKey(prefix, runId);
    const existing = operationKeys.current.get(key);
    if (existing) return existing;
    const created = `${key}-${crypto.randomUUID()}`;
    operationKeys.current.set(key, created);
    return created;
  };
  const latestEvent = useMemo(() => [...workflowEvents].reverse().find((event) => F05_EVENTS.includes(event.event_type)), [workflowEvents]);
  const inputs = initialState as Feature5Inputs;
  const exactSource = sourceVersion(initialState);
  const runtimeCandidates = inputs.runtime_candidates ?? [];
  const registrySnapshot = inputs.registry_snapshot;
  const planningJob = initialState.planning_job;
  const fingerprintMissing = Boolean(feasibility && !feasibility.package.workspace_fingerprint);
  const needsFingerprintRebind = fingerprintMissing || planningJob?.last_error_code === "PLANNING_WORKSPACE_FINGERPRINT_MISSING";

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setFeasibility(await getFeasibility(runId));
      setEmpty(false);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) setEmpty(true);
      else setError(`Feasibility could not be loaded. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`);
    } finally { setLoading(false); }
  }, [runId]);

  useEffect(() => { void refresh(); }, [refresh, initialState.state_version, latestEvent?.sequence]);

  async function resolve(operationPrefix = "feasibility") {
    setWorking(true); setError(null); setStale(false);
    try {
      await queueFeasibilityResolution(runId, { expected_state_version: initialState.state_version, idempotency_key: stableOperationKey(operationPrefix) });
      setEmpty(false);
      await refresh();
      await refreshAuthoritativeState?.();
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) { setStale(true); await refresh(); }
      else setError(`Feasibility resolution failed. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`);
    } finally { setWorking(false); }
  }

  async function submitDecision() {
    if (!feasibility) return;
    if (decision === "approve_with_comment" && !comment.trim()) { setError("Add a comment before approving with comment."); return; }
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await decideG05(runId, { expected_state_version: feasibility.state_version, idempotency_key: stableOperationKey("g05"), gate_version: feasibility.gate_version, package_checksum: feasibility.package_checksum, artifact_set_checksum: String(feasibility.package.artifact_set_checksum ?? ""), workspace_fingerprint: (feasibility.package.workspace_fingerprint as string | null | undefined) ?? null, plan_version: (feasibility.package.plan_version as string | null | undefined) ?? null, decision, comment: comment.trim() || null });
      setFeasibility((current) => current ? { ...current, gate_status: result.status, gate_decision: result.decision, state_version: result.state_version, event_sequence: result.event_sequence } : current);
      await refreshAuthoritativeState?.();
      await refresh();
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) { setStale(true); await refresh(); }
      else setError(`G05 decision failed. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`);
    } finally { setWorking(false); }
  }

  const approved = feasibility?.gate_status === "approved";
  const connectionLabel = connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..." : connectionStatus === "recovering" ? "Refreshing authoritative feasibility state..." : feasibility?.status ?? (working ? "in_progress" : "not loaded");
  return <section className={styles.panel} aria-labelledby="feasibility-title">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S2-F05</p><h2 id="feasibility-title">Feasibility and G05</h2><p className={styles.note}>Catalogue-owned compatibility truth; no local workflow advancement.</p></div><span className={styles.status}>{connectionLabel}</span></div>
    {loading ? <p role="status">Loading authoritative feasibility...</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {stale ? <p role="alert">The feasibility or G05 state is stale. The authoritative snapshot was reloaded; review the current package before retrying.</p> : null}
    {!loading && empty ? <><p className={styles.note}>No feasibility package is available yet.</p><button type="button" onClick={() => void resolve("feasibility")} disabled={working}>{working ? "Resolving feasibility..." : "Resolve route and Stage 1 profile"}</button>{!exactSource || !registrySnapshot?.checksum || !runtimeCandidates.length ? <p className={styles.note}>The backend will derive any missing source, runtime, catalogue, and registry evidence before feasibility runs.</p> : null}{planningJob ? <p className={planningJob.last_error_code ? styles.note : undefined} role={planningJob.last_error_code ? "alert" : "status"}>Planning job {planningJob.status} at {planningJob.current_step}{planningJob.last_error_code ? `: ${planningJob.last_error_code}${planningJob.last_error_message ? ` — ${planningJob.last_error_message}` : ""}` : ""}</p> : null}</> : null}
    {feasibility?.status === "in_progress" ? <p role="status">Compatibility resolution is running. This view will refresh from authoritative events and snapshots.</p> : null}
    {feasibility && needsFingerprintRebind ? <div role="alert"><p>This feasibility package is not bound to the approved G03 physical workspace. Regenerate it before approving G05 or generating a MigrationPlan.</p><button type="button" onClick={() => void resolve("feasibility-rebind")} disabled={working}>{working ? "Regenerating feasibility..." : "Regenerate fingerprint-bound feasibility"}</button></div> : null}
    {feasibility?.status === "blocked" ? <div role="alert"><p>Feasibility is blocked; G05 cannot approve this route.</p><ul className={styles.list}>{feasibility.blockers.map((item) => <li key={item}><code>{item}</code></li>)}</ul></div> : null}
    {feasibility ? <>
      <div className={styles.dimensionGrid} aria-label="Feasibility summary"><div><span>Source</span><strong>{feasibility.source_exact}</strong></div><div><span>Target</span><strong>{feasibility.target_family}</strong></div><div><span>Support</span><strong>{feasibility.support_level}</strong></div><div><span>Catalogue</span><strong>{feasibility.catalogue_snapshot?.version ?? "unknown"}</strong><code>{feasibility.catalogue_snapshot?.checksum ?? "checksum unavailable"}</code></div><div><span>Registry snapshot</span><strong>{feasibility.registry_snapshot?.snapshot_id ?? "unknown"}</strong><code>{feasibility.registry_snapshot?.checksum ?? "checksum unavailable"}</code></div></div>
      <h3>Major-stage ladder</h3><ol className={styles.list}>{feasibility.route.map((stage) => <li key={stage.stage_id}><strong>{stage.source_family} → {stage.target_family}</strong> <span className={styles.status}>{stage.support_level}</span>{stage.target_angular_exact ? <span> · Angular {stage.target_angular_exact} / CLI {stage.target_cli_exact}</span> : null}</li>)}</ol>
      {feasibility.warnings.length ? <div><h3>Warnings</h3><ul className={styles.list}>{feasibility.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      <div className={styles.previewPanel}><h3>Candidate runtimes</h3>{(feasibility.runtime_candidates ?? []).length ? <ul className={styles.list}>{(feasibility.runtime_candidates ?? []).map((candidate) => <li key={String(candidate.profile_id)}><strong>{String(candidate.profile_id)}</strong> · {String(candidate.operating_system)}/{String(candidate.architecture)} · Node {String(candidate.node_exact)} · npm {String(candidate.npm_exact)} · npx {String(candidate.npx_exact)}</li>)}</ul> : <p className={styles.note}>No runtime candidates were supplied by the authoritative backend.</p>}<h3>Exact Stage 1 profile</h3>{feasibility.selected_profile ? <div className={styles.dimensionGrid}><div><span>Angular / CLI</span><strong>{feasibility.selected_profile.angular_exact} / {feasibility.selected_profile.angular_cli_exact}</strong></div><div><span>Node / npm / npx</span><strong>{feasibility.selected_profile.node_exact} / {feasibility.selected_profile.npm_exact} / {feasibility.selected_profile.npx_exact}</strong></div><div><span>Profile</span><strong>{feasibility.selected_profile.profile_id}</strong></div><div><span>Checksum</span><code>{feasibility.selected_profile.checksum}</code></div></div> : <p className={styles.note}>No exact Stage 1 profile was resolved.</p>}</div>
      <div className={styles.previewPanel}><h3>Immutable evidence</h3><ul className={styles.list}>{feasibility.artifact_ids.map((id) => <li key={id}><a className={styles.actionLink} href={feasibility.artifact_links[id] ?? `/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a><code>{feasibility.artifact_checksums[id]}</code></li>)}</ul></div>
       <div className={styles.previewPanel}><h3>G05: {feasibility.gate_status}</h3>{approved ? <p role="status">G05 was accepted by the authoritative backend. This control does not locally advance the workflow.</p> : feasibility.gate_status === "blocked" ? <p role="alert">G05 is blocked until the feasibility evidence is renewed.</p> : <><label htmlFor="g05-decision">Decision</label><select id="g05-decision" value={decision} onChange={(event) => setDecision(event.target.value as G05Decision)}>{decisions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><label htmlFor="g05-comment">Review comment</label><textarea id="g05-comment" value={comment} onChange={(event) => setComment(event.target.value)} rows={3} placeholder="Optional rationale; required for approval with comment." /><button type="button" onClick={() => void submitDecision()} disabled={working || feasibility.gate_status !== "pending" || fingerprintMissing}>{working ? "Recording decision..." : "Record G05 decision"}</button></>}</div>
    </> : null}
  </section>;
}
