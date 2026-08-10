"use client";

import { useEffect, useState } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { G06Decision, PlanReviewChanges } from "@/types/planning";
import { usePlanReview } from "@/hooks/usePlanReview";
import styles from "./ControlTowerShell.module.css";
import panelStyles from "./MigrationPlanPanel.module.css";
import { headingTag, type PanelHeadingLevel } from "./control-tower/semanticHeading";

const fields: Array<{ key: keyof PlanReviewChanges; label: string }> = [
  { key: "catalogue_version", label: "Catalogue version" }, { key: "execution_profile_id", label: "Execution profile" },
  { key: "target_cli_exact", label: "Target CLI exact" }, { key: "validation_policy_id", label: "Validation policy" },
  { key: "recovery_policy_id", label: "Recovery policy" }, { key: "repair_policy_id", label: "Repair policy" }, { key: "builder", label: "Builder" },
];
const text = (value: unknown) => typeof value === "string" ? value : "";

export function PlanReviewPanel({ runId, initialState, connectionStatus, refreshAuthoritativeState, headingLevel = 2 }: { runId: string; initialState: AuthoritativeRunStateDto; connectionStatus: string; refreshAuthoritativeState: () => Promise<unknown>; headingLevel?: PanelHeadingLevel }) {
  const Heading = headingTag(headingLevel);
  const Subheading = headingTag(headingLevel, 1);
  const DetailHeading = headingTag(headingLevel, 2);
  const { review, status, error, lastAction, revise, explain, decide } = usePlanReview({ runId, stateVersion: initialState.state_version, workflowEvents: initialState.workflow_events, planningJob: initialState.planning_job, connectionStatus, refreshAuthoritativeState });
  const [changes, setChanges] = useState<PlanReviewChanges>({});
  const [comment, setComment] = useState("");
  const [selectedVersion, setSelectedVersion] = useState("current");
  const [notice, setNotice] = useState<string | null>(null);
  const planVersion = typeof review?.plan?.version === "number" ? review.plan.version : null;
  const priorVersion = review?.diff?.from_version;
  const canMutate = Boolean(review?.plan && review.stage_plan && review.plan_checksum);
  const gateBlocked = !canMutate || !review?.package_checksum || ["stale", "rejected", "blocked"].includes(review?.gate_status ?? "");
  const narrative = review?.package?.narrative && typeof review.package.narrative === "object" ? review.package.narrative as Record<string, unknown> : null;
  const artifactIds = Array.isArray(review?.artifact_ids) ? review.artifact_ids : [];
  useEffect(() => { if (status === "success") setNotice(null); }, [status, review?.plan_checksum]);
  function updateField(key: keyof PlanReviewChanges, value: string) { setChanges((current) => ({ ...current, [key]: value })); }
  async function submitRevision() { const selected = Object.fromEntries(Object.entries(changes).filter(([, value]) => value)); if (!Object.keys(selected).length) { setNotice("Choose at least one approved plan field to revise."); return; } setNotice(null); await revise(selected); }
  async function submitDecision(decision: G06Decision) { if (decision === "approve_with_comment" && !comment.trim()) { setNotice("Add a comment before approving with comment."); return; } setNotice(null); await decide(decision, comment.trim() || null); }
  return <section className={styles.panel} aria-labelledby="plan-review-title">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S2-F07-I03</p><Heading id="plan-review-title">Review and approve MigrationPlan</Heading><p className={styles.note}>Executable plan data and Planning Agent interpretation are separate evidence.</p></div><span className={styles.status}>{status === "running" ? `${lastAction ?? "Working"}…` : status}</span></div>
    {status === "reconnecting" ? <p role="status">Connection interrupted. Reloading the authoritative review after reconnect.</p> : null}{status === "loading" ? <p role="status">Loading authoritative plan review…</p> : null}{status === "empty" ? <p className={styles.note}>No persisted plan review is available yet. Generate the MigrationPlan first.</p> : null}{status === "authorization" ? <p role="alert">You are not authorized to review this migration plan.</p> : null}{status === "blocked" ? <p role="alert">Plan review is blocked by missing or invalid evidence. G06 cannot advance.</p> : null}{status === "stale" ? <p className={panelStyles.stale} role="alert">This review is stale. The authoritative snapshot was refreshed; select the current version before retrying.</p> : null}{error ? <p role="alert">{error}</p> : null}
    {review ? <>
      <div className={panelStyles.grid}><div><span>Plan version</span><strong>{planVersion ?? "—"}</strong></div><div><span>Plan checksum</span><code>{review.plan_checksum ?? "—"}</code></div><div><span>Stage checksum</span><code>{review.stage_plan_checksum ?? "—"}</code></div><div><span>G06</span><strong>{review.gate_status}</strong></div></div>
      <label className={panelStyles.field}>Plan version<select aria-label="Plan version" value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)}><option value="current">Current{planVersion ? ` (v${planVersion})` : ""}</option>{priorVersion ? <option value="previous">Previous (v{priorVersion})</option> : null}</select></label>
      {selectedVersion === "previous" ? <p className={styles.note}>The previous immutable version is represented by the backend diff below; executable actions remain bound to the current checksum.</p> : null}
      {review.diff ? <div aria-label="Plan version diff"><Subheading>Immutable version diff</Subheading><p>v{review.diff.from_version} → v{review.diff.to_version}</p><ul className={styles.list}>{(review.diff.changed_fields ?? []).map((field) => <li key={field}><code>{field}</code>{review.diff?.changes?.[field] !== undefined ? `: ${JSON.stringify(review.diff.changes[field])}` : null}</li>)}</ul><code>{review.diff.checksum ?? ""}</code></div> : <p className={styles.note}>No revision diff has been recorded.</p>}
      <div className={panelStyles.reviewGrid}><div><Subheading>Bounded revision</Subheading><p className={styles.note}>Only approved policy, catalogue, profile, CLI, and builder fields can be changed.</p>{fields.map(({ key, label }) => <label className={panelStyles.field} key={key}>{label}<input value={text(changes[key])} onChange={(event) => updateField(key, event.target.value)} /></label>)}<button className={panelStyles.action} type="button" onClick={() => void submitRevision()} disabled={!canMutate || status === "running"}>Create immutable revision</button></div>
      <div><Subheading>Planning explanation</Subheading><p className={styles.note}>Model narrative is advisory and cannot change the executable plan or checksum.</p>{narrative ? <><p>{text(narrative.summary)}</p><DetailHeading>Rationale</DetailHeading><ul className={styles.list}>{Array.isArray(narrative.rationale) ? narrative.rationale.map((item) => <li key={String(item)}>{String(item)}</li>) : null}</ul><DetailHeading>Risks</DetailHeading><ul className={styles.list}>{Array.isArray(narrative.risks) ? narrative.risks.map((item) => <li key={String(item)}>{String(item)}</li>) : null}</ul></> : <p className={styles.note}>No explanation has been generated for this checksum.</p>}<button className={panelStyles.action} type="button" onClick={() => void explain()} disabled={!canMutate || status === "running"}>Request explanation</button></div></div>
      <div><Subheading>G06 decision</Subheading><p className={styles.note}>Gate decisions are backend-authoritative and checksum-bound.</p><label className={panelStyles.field}>Comment<textarea value={comment} onChange={(event) => setComment(event.target.value)} maxLength={4000} /></label><div className={panelStyles.actions}><button className={panelStyles.action} type="button" onClick={() => void submitDecision("approve")} disabled={gateBlocked || status === "running"}>Approve G06</button><button className={panelStyles.action} type="button" onClick={() => void submitDecision("approve_with_comment")} disabled={gateBlocked || status === "running"}>Approve with comment</button><button className={panelStyles.action} type="button" onClick={() => void submitDecision("request_modification")} disabled={gateBlocked || status === "running"}>Request modification</button><button className={panelStyles.action} type="button" onClick={() => void submitDecision("reject")} disabled={gateBlocked || status === "running"}>Reject</button></div></div>
      <div><Subheading>Registered evidence</Subheading>{artifactIds.length > 0 ? <ul className={styles.list}>{artifactIds.map((id) => <li key={id}><a href={review.artifact_links?.[id] ?? `/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a> <code>{review.artifact_checksums?.[id] ?? ""}</code></li>)}</ul> : <p className={styles.note}>No reviewer artifacts are available.</p>}</div>
    </> : null}{notice ? <p role="alert">{notice}</p> : null}
  </section>;
}
