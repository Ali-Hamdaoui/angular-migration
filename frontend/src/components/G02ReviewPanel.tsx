"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError, getBackendBaseUrl } from "@/api/client";
import { decideG02, getG02Review, initializeG02 } from "@/api/g02";
import type { AuthoritativeRunStateDto, G02Decision, G02ReviewResponse, WorkflowEventDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

const decisions: Array<{ value: G02Decision; label: string }> = [
  { value: "approved", label: "Approve G02" },
  { value: "approved_with_comment", label: "Approve with comment" },
  { value: "modification_requested", label: "Request modification" },
  { value: "rejected", label: "Reject G02" },
];

function latestG02Event(events: WorkflowEventDto[]) {
  return [...events].reverse().find((event) => ["G02_CREATED", "G02_APPROVED", "G02_REJECTED", "G02_STALE", "SOURCE_INTEGRITY_VERIFIED", "SOURCE_INTEGRITY_FAILED"].includes(event.event_type));
}

export function G02ReviewPanel({ runId, initialState }: { runId: string; initialState: AuthoritativeRunStateDto }) {
  const [review, setReview] = useState<G02ReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [selectedDecision, setSelectedDecision] = useState<G02Decision>("approved");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const event = useMemo(() => latestG02Event(initialState.workflow_events), [initialState.workflow_events]);

  const refresh = useCallback(() => {
    setLoading(true);
    getG02Review(runId).then((value) => { setReview(value); setMissing(false); }).catch((reason: unknown) => {
      if (reason instanceof ApiClientError && reason.status === 404) setMissing(true);
      else setError("G02 review evidence could not be loaded.");
    }).finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => { refresh(); }, [refresh, event?.sequence]);

  async function initializePackage() {
    setSubmitting(true); setError(null);
    try {
      const result = await initializeG02(runId, { expected_state_version: initialState.state_version, idempotency_key: `g02-package-${runId}-${Date.now()}`, actor: "control-tower", gate_id: "G02" });
      setReview(result); setMissing(false);
    } catch { setError("The G02 evidence package could not be created. Refresh the authoritative run state and retry."); }
    finally { setSubmitting(false); }
  }
  async function submitDecision() {
    if (selectedDecision === "approved_with_comment" && !comment.trim()) { setError("Add a comment before approving with comment."); return; }
    setSubmitting(true); setError(null);
    try {
      const result = await decideG02(runId, {
        expected_state_version: review?.state_version ?? initialState.state_version,
        idempotency_key: `g02-${runId}-${selectedDecision}-${review?.package.package_checksum ?? "new"}`,
        actor: "control-tower", decision: selectedDecision, comment: comment.trim() || null, gate_id: "G02",
      });
      setReview(result); setMissing(false);
    } catch (reason: unknown) {
      setError(reason instanceof ApiClientError && reason.status === 409 ? "G02 is stale. Refresh the authoritative run state before deciding." : "The G02 decision could not be recorded.");
    } finally { setSubmitting(false); }
  }

  const packageData = review?.package;
  const integrity = packageData?.integrity;
  const approved = review?.status === "approved" || review?.status === "approved_with_comment";

  return <section className={styles.panel} aria-label="G02 source integrity review">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S1-F08</p><h2>G02 source-integrity boundary</h2></div>{review ? <strong>{review.status}</strong> : null}</div>
    {loading ? <p className={styles.note}>Loading G02 evidence...</p> : null}
    {!loading && missing ? <div><p className={styles.note}>G02 is pending. Initialize the review package from the finalized immutable snapshot.</p><button type="button" onClick={initializePackage} disabled={submitting}>Initialize G02 review</button></div> : null}
    {event?.event_type === "SOURCE_INTEGRITY_FAILED" ? <p role="alert">Source integrity failed. Approval is blocked until the source boundary is resolved.</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {packageData ? <>
      <div className={styles.dimensionGrid} aria-label="G02 integrity summary"><div><span>Integrity</span><strong>{integrity?.status ?? "unknown"}</strong></div><div><span>Policy</span><strong>{packageData.policy_version}</strong></div><div><span>State version</span><strong>{review?.state_version}</strong></div><div><span>Boundary</span><strong>{review?.baseline_input_boundary ?? "Not established"}</strong></div></div>
      <dl className={styles.metadataGrid}><div><dt>Source fingerprint</dt><dd>{packageData.source_fingerprint}</dd></div><div><dt>After-snapshot fingerprint</dt><dd>{integrity?.after_snapshot_fingerprint}</dd></div><div><dt>Snapshot fingerprint</dt><dd>{packageData.snapshot_fingerprint}</dd></div><div><dt>Package checksum</dt><dd>{packageData.package_checksum}</dd></div></dl>
      {integrity && integrity.before_fingerprint !== integrity.after_snapshot_fingerprint ? <p role="alert">The original source changed after snapshot creation. This package cannot be approved.</p> : null}
      <h3>Immutable evidence</h3><ul className={styles.list}>{packageData.artifacts.map((artifact) => <li key={artifact.artifact_id}><a className={styles.actionLink} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`}>{artifact.relative_path}</a><code>{artifact.checksum}</code></li>)}</ul>
      {approved ? <p className={styles.note}>Baseline input boundary: immutable snapshot {review?.baseline_input_boundary}.</p> : <><p className={styles.note}>Next step blocked until G02 is approved with verified source integrity.</p><div className={styles.previewPanel}><label htmlFor="g02-decision">Decision</label><select id="g02-decision" value={selectedDecision} onChange={(e) => setSelectedDecision(e.target.value as G02Decision)}>{decisions.map((decision) => <option key={decision.value} value={decision.value}>{decision.label}</option>)}</select><label htmlFor="g02-comment">Comment</label><textarea id="g02-comment" value={comment} onChange={(e) => setComment(e.target.value)} rows={3} placeholder="Optional rationale; required for approval with comment." /><button type="button" onClick={submitDecision} disabled={submitting || integrity?.status !== "verified"}>{submitting ? "Recording decision..." : "Record G02 decision"}</button></div></>}
    </> : null}
  </section>;
}
