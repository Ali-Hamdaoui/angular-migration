"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getExecutionProfiles } from "@/api/executionProfiles";
import { getStagePlan } from "@/api/plans";
import { getTransformationEvidence, getAngularUpdate, getTargetVersionTyped, startAngularUpdate, verifyTargetVersion } from "@/api/transformations";
import type { ArtifactRefDto, ExecutionProfile } from "@/types/generated/api";
import type { AngularUpdateResponse, TargetVersionResponse, TransformationEvidenceResponse } from "@/types/transformation";
import type { WorkflowEventDto } from "@/types/generated/api";
import { StatusPill } from "@/components/StatusPill";
import styles from "./ControlTowerShell.module.css";

type ViewState = "loading" | "empty" | "running" | "pending_verification" | "success" | "blocked" | "stale" | "reconnecting" | "failure" | "cancelled" | "no_evidence";

interface Props {
  runId: string; stageId: string; expectedStateVersion: number;
  onStateChange?: (newVersion: number) => void; workflowEvents?: WorkflowEventDto[]; artifacts?: ArtifactRefDto[]; connectionStatus?: "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";
}

const artifactHref = (id: string) => `/api/v1/artifacts/${encodeURIComponent(id)}`;
const text = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "—";

export function AngularUpdatePanel({ runId, stageId, expectedStateVersion, onStateChange, workflowEvents = [], artifacts = [], connectionStatus = "open" }: Props) {
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [update, setUpdate] = useState<AngularUpdateResponse | null>(null);
  const [target, setTarget] = useState<TargetVersionResponse | null>(null);
  const [evidence, setEvidence] = useState<TransformationEvidenceResponse | null>(null);
  const [plan, setPlan] = useState<Awaited<ReturnType<typeof getStagePlan>>["stage_plan"] | null>(null);
  const [planArtifactIds, setPlanArtifactIds] = useState<string[]>([]);
  const [profile, setProfile] = useState<ExecutionProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const verifiedEventRef = useRef(false);
  const seenEvents = useRef(new Set<string>());
  const submittingKind = useRef<"start" | "verify" | null>(null);

  const log = useCallback((value: string) => setLogs((items) => [...items, value]), []);
  const applyResult = useCallback((result: AngularUpdateResponse) => {
    setUpdate(result);
    if (result.target_version_status === "verified" && verifiedEventRef.current) setViewState("success");
    else if (result.status === "failed" || result.target_version_status === "failed" || result.target_version_status === "mismatch") setViewState("failure");
    else if (result.status === "interactive_blocked") setViewState("blocked");
    else if (result.status === "running") setViewState("running");
    else if (result.status === "succeeded") setViewState("pending_verification");
    else setViewState("empty");
    if (result.error_message) setError(result.error_message);
  }, []);

  const refresh = useCallback(async () => {
    setViewState("reconnecting");
    try {
      const [result, lockedPlan, profiles, transformEvidence] = await Promise.all([
        getAngularUpdate(runId, stageId), getStagePlan(runId, stageId), getExecutionProfiles(runId), getTransformationEvidence(runId, stageId),
      ]);
      setPlan(lockedPlan.stage_plan); setPlanArtifactIds(lockedPlan.artifact_ids); setEvidence(transformEvidence);
      applyResult(result);
      setProfile(profiles.selected_profile ?? profiles.compatible_profiles.find((item) => item.profile_id === lockedPlan.stage_plan.execution_profile_id) ?? null);
      try { setTarget(await getTargetVersionTyped(runId, stageId)); } catch { /* update state remains authoritative */ }
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) { setViewState("stale"); setError("The locked plan or run state changed. Refresh the authoritative snapshot."); }
      else if (reason instanceof ApiClientError && (reason.status === 401 || reason.status === 403)) { setViewState("failure"); setError("You are not authorized to view or run this stage."); }
      else if (reason instanceof ApiClientError && reason.status === 404) setViewState("no_evidence");
      else { setViewState("no_evidence"); setError("Angular update evidence could not be loaded."); }
    }
  }, [runId, stageId, applyResult]);

  useEffect(() => { void refresh(); }, [refresh, expectedStateVersion]);
  useEffect(() => { if (connectionStatus === "reconnecting" || connectionStatus === "recovering") setViewState("reconnecting"); }, [connectionStatus]);

  useEffect(() => {
    for (const event of workflowEvents) {
      if (event.run_id !== runId || event.stage_id !== stageId || seenEvents.current.has(event.event_id)) continue;
      seenEvents.current.add(event.event_id);
      const payload = event.payload ?? {};
      if (event.event_type === "TARGET_VERSION_VERIFIED") { verifiedEventRef.current = true; setViewState("success"); log("Target version verified by backend (SSE)."); }
      else if (event.event_type === "TARGET_VERSION_FAILED") { setViewState("failure"); setError("Target version verification failed."); }
      else if (event.event_type === "INTERACTIVE_DECISION_REQUIRED") { setViewState("blocked"); setError("Interactive prompt detected. Manual intervention is required."); }
      else if (event.event_type === "COMMAND_CANCELLED" || event.event_type === "COMMAND_INTERRUPTED") { setViewState("cancelled"); setError("Angular update was cancelled."); }
      else if (event.event_type === "ANGULAR_UPDATE_FAILED") { setViewState("failure"); setError(typeof payload.error_message === "string" ? payload.error_message : "Angular update failed."); }
      else if ((event.event_type === "COMMAND_OUTPUT_CHUNK" || event.event_type === "COMMAND_OUTPUT_AVAILABLE") && typeof payload.chunk === "string") setLogs((items) => [...items, payload.chunk as string]);
      else if (event.event_type === "ANGULAR_UPDATE_COMPLETED") setViewState("pending_verification");
      if (typeof payload.state_version === "number") onStateChange?.(payload.state_version);
    }
  }, [workflowEvents, runId, stageId, onStateChange, log]);

  async function start() {
    if (submittingKind.current) return; submittingKind.current = "start"; setSubmitting(true); setViewState("running");
    try {
      if (!plan) return;
      const result = await startAngularUpdate(runId, stageId, { expected_state_version: expectedStateVersion, idempotency_key: `angular-update-${runId}-${stageId}`, actor: "operator", source_version: plan.source_exact, target_version: plan.target_exact, toolchain_profile_id: plan.execution_profile_id, prerequisite_artifact_ids: planArtifactIds });
      applyResult(result); onStateChange?.(result.state_version);
    } catch (reason: unknown) {
      setViewState(reason instanceof ApiClientError && reason.status === 409 ? "stale" : reason instanceof ApiClientError && [401, 403].includes(reason.status) ? "failure" : "failure");
      setError(reason instanceof ApiClientError && reason.status === 403 ? "You are not authorized to run this stage." : "Angular update could not be started.");
    } finally { submittingKind.current = null; setSubmitting(false); }
  }

  async function verify() {
    if (submittingKind.current) return; submittingKind.current = "verify"; setSubmitting(true);
    if (!update?.command_execution_id) { submittingKind.current = null; setSubmitting(false); setViewState("failure"); setError("The authoritative command execution is not available for verification."); return; }
    try { const result = await verifyTargetVersion(runId, stageId, { expected_state_version: expectedStateVersion, idempotency_key: `angular-target-verify-${runId}-${stageId}`, actor: "operator", command_execution_id: update.command_execution_id }); setTarget(result); setViewState(result.target_version_status === "mismatch" || result.target_version_status === "failed" ? "failure" : "pending_verification"); if (result.state_version) onStateChange?.(result.state_version); }
    catch (reason: unknown) { setViewState(reason instanceof ApiClientError && reason.status === 409 ? "stale" : "failure"); setError("Target verification could not be completed."); }
    finally { submittingKind.current = null; setSubmitting(false); }
  }

  const stateLabel = viewState === "success" ? "PASSED" : viewState === "failure" || viewState === "cancelled" ? "FAILED" : viewState === "blocked" ? "BLOCKED" : viewState === "stale" || viewState === "no_evidence" ? "WARNING" : "RUNNING";
  const command = plan?.commands.angular_update?.[0];
  const lockedSourceVersion = plan?.source_exact ?? "locked plan unavailable";
  const lockedTargetVersion = plan?.target_exact ?? "locked plan unavailable";
  const evidenceIds = [...new Set([...(update?.artifact_ids ?? []), ...(target?.artifact_ids ?? []), ...(evidence?.artifacts ?? []).map((a) => a.artifact_id), ...artifacts.filter((item) => item.stage_id === stageId).map((item) => item.artifact_id)])];
  const evidenceRows = ["package_json_version", "lockfile_version", "dependency_tree_version", "ng_version_output"];

  if (viewState === "loading") return <section className={styles.panel} aria-labelledby="angular-update-title"><h2 id="angular-update-title">Angular Update</h2><p role="status">Loading authoritative Angular update evidence…</p></section>;
  return <section className={styles.panel} aria-labelledby="angular-update-title">
    <div className={styles.header}><div><p className={styles.kicker}>S3-F07-I03 · locked stage plan</p><h2 id="angular-update-title">Angular Update</h2></div><StatusPill value={stateLabel} /></div>
    <div className={styles.dimensionGrid} aria-label="Angular update dimensions"><div><span>Source version</span><strong>{lockedSourceVersion}</strong></div><div><span>Exact target</span><strong>{lockedTargetVersion}</strong></div><div><span>Stage</span><strong>{stageId}</strong></div><div><span>Execution ID</span><strong>{update?.command_execution_id ?? "pending"}</strong></div><div><span>State version</span><strong>{expectedStateVersion}</strong></div></div>
    {command ? <div className={styles.previewPanel}><h3>Registered command</h3><p><code>{command.executable} {command.arguments.join(" ")}</code></p><p className={styles.note}>Working directory: {command.working_directory_alias}; shell: disabled; network: {command.network_profile}</p></div> : null}
    {profile ? <div className={styles.previewPanel}><h3>Execution profile</h3><p><strong>{profile.profile_id}</strong> · Node {profile.node_exact} · npm {profile.package_manager_exact} · npx {profile.npx_exact}</p><p className={styles.note}>Profile checksum: <code>{profile.checksum}</code></p></div> : null}
    {target ? <div className={styles.previewPanel}><h3>Target verification matrix</h3><p>Backend status: <strong>{target.target_version_status}</strong> · resolved: <strong>{text(target.resolved_target_version)}</strong> · sources agree: <strong>{target.all_sources_agree ? "yes" : "no"}</strong></p><dl>{evidenceRows.map((key) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd><code>{target.evidence_sources[key] ?? "not available"}</code></dd></div>)}</dl>{target.disagreements.map((item) => <p role="alert" key={item}>{item}</p>)}</div> : null}
    {evidence ? <div className={styles.previewPanel}><h3>Applied migrations and evidence matrix</h3><ul>{(evidence.migration_list.length ? evidence.migration_list : ["No migration entries recorded"]).map((item) => <li key={item}><code>{item}</code></li>)}</ul><p className={styles.note}>Package manifest, lockfile, dependency tree, and local CLI evidence are backend artifacts; this UI does not infer their result from logs or exit codes.</p></div> : null}
    {evidenceIds.length ? <div className={styles.previewPanel}><h3>Artifact links</h3><ul className={styles.list}>{evidenceIds.map((id) => <li key={id}><a href={artifactHref(id)} target="_blank" rel="noreferrer">{id}</a></li>)}</ul></div> : null}
    <div className={styles.row}><span>{viewState === "pending_verification" ? "Execution finished; awaiting TARGET_VERSION_VERIFIED." : viewState === "reconnecting" ? "Reconnecting…" : "Backend-authoritative state"}</span>{viewState === "empty" ? <button type="button" onClick={() => void start()} disabled={submitting || !plan}>Start Angular update</button> : null}{viewState === "pending_verification" ? <button type="button" onClick={() => void verify()} disabled={submitting}>Verify target version</button> : null}</div>
    {viewState === "blocked" ? <p role="alert">{error ?? "Interactive prompt detected. Manual intervention is required."}</p> : null}
    {viewState === "stale" ? <p role="alert">{error}</p> : null}
    {viewState === "no_evidence" || viewState === "failure" || viewState === "cancelled" ? <p role="alert">{error ?? "No passing evidence is available."}</p> : null}
    {logs.length ? <pre aria-label="Angular update logs">{logs.join("\n")}</pre> : null}
  </section>;
}
