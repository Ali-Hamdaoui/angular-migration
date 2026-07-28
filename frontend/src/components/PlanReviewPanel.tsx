"use client";

import { useEffect, useState } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { G06Decision, PlanReviewChanges } from "@/types/planning";
import { usePlanReview } from "@/hooks/usePlanReview";
import styles from "./ControlTowerShell.module.css";
import panelStyles from "./MigrationPlanPanel.module.css";

const fields: Array<{ key: keyof PlanReviewChanges; label: string }> = [
  { key: "catalogue_version", label: "Catalogue version" }, { key: "execution_profile_id", label: "Execution profile" },
  { key: "target_cli_exact", label: "Target CLI exact" }, { key: "validation_policy_id", label: "Validation policy" },
  { key: "recovery_policy_id", label: "Recovery policy" }, { key: "repair_policy_id", label: "Repair policy" }, { key: "builder", label: "Builder" },
];
const text = (value: unknown) => typeof value === "string" ? value : "";

export function PlanReviewPanel({ runId, initialState, connectionStatus, refreshAuthoritativeState }: { runId: string; initialState: AuthoritativeRunStateDto; connectionStatus: string; refreshAuthoritativeState: () => Promise<unknown> }) {
  const { review, status, error, lastAction, revise, explain, decide } = usePlanReview({ runId, stateVersion: initialState.state_version, workflowEvents: initialState.workflow_events, planningJob: initialState.planning_job, connectionStatus, refreshAuthoritativeState });
  const [changes, setChanges] = useState<PlanReviewChanges>({});
  const [comment, setComment] = useState("");
  const [selectedVersion, setSelectedVersion] = useState("current");
  const [notice, setNotice] = useState<string | null>(null);
  const planVersion = typeof review?.plan?.version === "number" ? review.plan.version : null;
  const priorVersion = review?.diff?.from_version;
  const artifactSetChecksum = review?.computed_artifact_set_checksum ?? review?.artifact_set_checksum ?? null;
  const artifactIntegrityValid = Boolean(review?.artifact_ids.length && review.artifact_ids.every((id) => Boolean(review.artifact_checksums[id])));
  const stateVersionCurrent = review?.state_version === initialState.state_version;
  const canMutate = Boolean(review?.plan && review.stage_plan && review.plan_checksum && review.stage_plan_checksum && artifactSetChecksum && artifactIntegrityValid && stateVersionCurrent);
  const jobReadyForG06 = !initialState.planning_job || initialState.planning_job.status === "waiting_g06";
  const gateBlocked = !canMutate || !review?.package_checksum || !jobReadyForG06 || ["stale", "rejected", "blocked", "expired"].includes(review?.gate_status ?? "");
  const narrative = review?.package?.narrative && typeof review.package.narrative === "object" ? review.package.narrative as Record<string, unknown> : null;
  const approvedForPreparation = initialState.status === "WAITING_STAGE_PREPARATION" || initialState.planning_job?.status === "completed";
  useEffect(() => { if (status === "success") setNotice(null); }, [status, review?.plan_checksum]);
  function updateField(key: keyof PlanReviewChanges, value: string) { setChanges((current) => ({ ...current, [key]: value })); }
  async function submitRevision() { const selected = Object.fromEntries(Object.entries(changes).filter(([, value]) => value)); if (!Object.keys(selected).length) { setNotice("Choose at least one approved plan field to revise."); return; } setNotice(null); await revise(selected); }
  async function submitDecision(decision: G06Decision) { if (decision === "approve_with_comment" && !comment.trim()) { setNotice("Add a comment before approving with comment."); return; } setNotice(null); await decide(decision, comment.trim() || null); }
  return <section className={styles.panel} aria-labelledby="plan-review-title">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S2-F07-I03</p><h2 id="plan-review-title">Review and approve MigrationPlan</h2><p className={styles.note}>Executable plan data and Planning Agent interpretation are separate evidence.</p></div><span className={styles.status}>{status === "running" ? `${lastAction ?? "Working"}…` : status}</span></div>
    {approvedForPreparation ? <p role="status"><strong>Plan approved for execution. Waiting for authoritative stage preparation.</strong></p> : null}
    {status === "reconnecting" ? <p role="status">Connection interrupted. Reloading the authoritative review after reconnect.</p> : null}{status === "loading" ? <p role="status">Loading authoritative plan review…</p> : null}{status === "empty" ? <p className={styles.note}>No persisted plan review is available yet. The backend will create it automatically after G05 approval and plan generation.</p> : null}{status === "authorization" ? <p role="alert">You are not authorized to review this migration plan.</p> : null}{status === "blocked" ? <p role="alert">Plan review is blocked by missing or invalid evidence. G06 cannot advance.</p> : null}{status === "stale" ? <p className={panelStyles.stale} role="alert">This review is stale. The authoritative snapshot was refreshed; inspect the current package before deciding again.</p> : null}{error ? <p role="alert">{error}</p> : null}
    {review ? <>
      <div className={panelStyles.grid}><div><span>Plan version</span><strong>{planVersion ?? "—"}</strong></div><div><span>Plan checksum</span><code>{review.plan_checksum ?? "—"}</code></div><div><span>Stage checksum</span><code>{review.stage_plan_checksum ?? "—"}</code></div><div><span>Artifact-set checksum</span><code>{artifactSetChecksum ?? "—"}</code></div><div><span>G06</span><strong>{review.gate_status}</strong></div></div>
      <label className={panelStyles.field}>Plan version<select aria-label="Plan version" value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)}><option value="current">Current{planVersion ? ` (v${planVersion})` : ""}</option>{priorVersion ? <option value="previous">Previous (v{priorVersion})</option> : null}</select></label>
      {selectedVersion === "previous" ? <p className={styles.note}>The previous immutable version is represented by the backend diff below; executable actions remain bound to the current checksum.</p> : null}
      {review.diff ? <div aria-label="Plan version diff"><h3>Immutable version diff</h3><p>v{review.diff.from_version} → v{review.diff.to_version}</p><ul className={styles.list}>{(review.diff.changed_fields ?? []).map((field) => <li key={field}><code>{field}</code>{review.diff?.changes?.[field] !== undefined ? `: ${JSON.stringify(review.diff.changes[field])}` : null}</li>)}</ul><code>{review.diff.checksum ?? ""}</code></div> : <p className={styles.note}>No revision diff has been recorded.</p>}
      <div className={panelStyles.reviewGrid}><div><h3>Bounded revision</h3><p className={styles.note}>Only approved policy, catalogue, profile, CLI, and builder fields can be changed.</p>{fields.map(({ key, label }) => <label className={panelStyles.field} key={key}>{label}<input value={text(changes[key])} onChange={(event) => updateField(key, event.target.value)} /></label>)}<button className={panelStyles.action} type="button" onClick={() => void submitRevision()} disabled={!canMutate || status === "running"}>Create immutable revision</button></div>
      <div><h3>Planning explanation</h3><p className={styles.note}>Model narrative is advisory and cannot change the executable plan or checksum.</p>{narrative ? <><p>{text(narrative.summary)}</p><h4>Rationale</h4><ul className={styles.list}>{Array.isArray(narrative.rationale) ? narrative.rationale.map((item) => <li key={String(item)}>{String(item)}</li>) : null}</ul><h4>Risks</h4><ul className={styles.list}>{Array.isArray(narrative.risks) ? narrative.risks.map((item) => <li key={String(item)}>{String(item)}</li>) : null}</ul></> : <p className={styles.note}>No explanation has been generated for this checksum.</p>}<button className={panelStyles.action} type="button" onClick={() => void explain()} disabled={!canMutate || status === "running"}>Request explanation</button></div></div>
      <div><h3>G06 decision</h3><p className={styles.note}>Gate decisions are backend-authoritative and checksum-bound.</p><label className={panelStyles.field}>Comment<textarea value={comment} onChange={(event) => setComment(event.target.value)} maxLength={4000} /></label>{!jobReadyForG06 ? <p className={styles.note}>G06 decisions are disabled until the durable planning job reaches waiting_g06.</p> : null}<div className={panelStyles.actions}><button className={panelStyles.action} type="button" onClick={() => void submitDecision("approve")} disabled={gateBlocked || status === "running"}>Approve G06</button><button className={panelStyles.action} type="button" onClick={() => void submitDecision("approve_with_comment")} disabled={gateBlocked || status === "running"}>Approve with comment</button><button className={panelStyles.action} type="button" onClick={() => void submitDecision("request_modification")} disabled={gateBlocked || status === "running"}>Request modification</button><button className={panelStyles.action} type="button" onClick={() => void submitDecision("reject")} disabled={gateBlocked || status === "running"}>Reject</button></div></div>
      <div><h3>Registered evidence</h3><ul className={styles.list}>{review.artifact_ids.map((id) => <li key={id}><a href={review.artifact_links[id] ?? `/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a> <code>{review.artifact_checksums[id] ?? ""}</code></li>)}</ul></div>
    </> : null}{notice ? <p role="alert">{notice}</p> : null}
  </section>;
}
