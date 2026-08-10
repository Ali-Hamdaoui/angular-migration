"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError, getBackendBaseUrl } from "@/api/client";
import { decideG02, getG02Review, initializeG02 } from "@/api/g02";
import type { AuthoritativeRunStateDto, G02Decision, G02ReviewResponse, WorkflowEventDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";
import { headingTag, type PanelHeadingLevel } from "./control-tower/semanticHeading";
import type { AuthoritativePackageLoad } from "./control-tower/authoritativePackageLoad";

const decisions: Array<{ value: G02Decision; label: string }> = [
  { value: "approved", label: "Approve G02" },
  { value: "approved_with_comment", label: "Approve with comment" },
  { value: "modification_requested", label: "Request modification" },
  { value: "rejected", label: "Reject G02" },
];

function latestG02Event(events: WorkflowEventDto[]) {
  return [...events].reverse().find((event) => ["G02_CREATED", "G02_APPROVED", "G02_REJECTED", "G02_STALE", "SOURCE_INTEGRITY_VERIFIED", "SOURCE_INTEGRITY_FAILED"].includes(event.event_type));
}

function reviewBinding(review: G02ReviewResponse): string {
  return `${review.run_id}|${review.package.package_checksum}|${review.event_sequence}|${review.state_version}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validatedDecisionResponse(
  value: unknown,
  submittedReview: G02ReviewResponse,
  runId: string,
  submittedDecision: G02Decision,
): G02ReviewResponse | null {
  if (!isRecord(value) || !isRecord(value.package)) return null;
  const packageData = value.package;
  const approved = submittedDecision === "approved" || submittedDecision === "approved_with_comment";
  const validBoundary = approved
    ? value.baseline_input_boundary === submittedReview.package.snapshot_id
    : value.baseline_input_boundary === null;

  if (
    submittedReview.run_id !== runId
    || submittedReview.gate_id !== "G02"
    || submittedReview.package.run_id !== runId
    || submittedReview.package.gate_id !== "G02"
    || value.run_id !== runId
    || value.gate_id !== "G02"
    || value.gate_version !== submittedReview.gate_version
    || value.status !== submittedDecision
    || value.decision !== submittedDecision
    || packageData.run_id !== runId
    || packageData.gate_id !== "G02"
    || packageData.gate_version !== submittedReview.package.gate_version
    || packageData.package_checksum !== submittedReview.package.package_checksum
    || packageData.artifact_set_checksum !== submittedReview.package.artifact_set_checksum
    || packageData.snapshot_id !== submittedReview.package.snapshot_id
    || packageData.state_version !== submittedReview.package.state_version
    || !Number.isInteger(value.state_version)
    || Number(value.state_version) <= submittedReview.state_version
    || !Number.isInteger(value.event_sequence)
    || Number(value.event_sequence) <= submittedReview.event_sequence
    || typeof value.idempotent_replay !== "boolean"
    || value.stale_reason !== null
    || !(value.comment === null || typeof value.comment === "string")
    || !validBoundary
  ) return null;

  return {
    run_id: runId,
    gate_id: "G02",
    gate_version: submittedReview.gate_version,
    status: submittedDecision,
    decision: submittedDecision,
    package: submittedReview.package,
    baseline_input_boundary: approved ? submittedReview.package.snapshot_id : null,
    state_version: Number(value.state_version),
    event_sequence: Number(value.event_sequence),
    idempotent_replay: value.idempotent_replay,
    stale_reason: null,
    comment: value.comment,
  };
}

type G02ReviewPanelProps = {
  runId: string;
  initialState: AuthoritativeRunStateDto;
  authoritativeReview?: AuthoritativePackageLoad<G02ReviewResponse>;
  refreshAuthoritativeState?: () => Promise<void>;
  headingLevel?: PanelHeadingLevel;
};

export function G02ReviewPanel({ runId, initialState, authoritativeReview, refreshAuthoritativeState, headingLevel = 2 }: G02ReviewPanelProps) {
  const Heading = headingTag(headingLevel);
  const Subheading = headingTag(headingLevel, 1);
  const externallyLoaded = authoritativeReview !== undefined;
  const [localReview, setReview] = useState<G02ReviewResponse | null>(null);
  const [decisionOverride, setDecisionOverride] = useState<{ binding: string; value: G02ReviewResponse } | null>(null);
  const [invalidDecisionBinding, setInvalidDecisionBinding] = useState<string | null>(null);
  const [loading, setLoading] = useState(!externallyLoaded);
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

  useEffect(() => { if (!externallyLoaded) refresh(); }, [event?.sequence, externallyLoaded, refresh]);

  const externalReview = externallyLoaded && authoritativeReview.status === "ready" ? authoritativeReview.value : null;
  const externalBinding = externalReview ? reviewBinding(externalReview) : null;
  const review = externallyLoaded
    ? decisionOverride?.binding === externalBinding ? decisionOverride.value : externalReview
    : localReview;
  const decisionValidationBlocked = externallyLoaded && invalidDecisionBinding === externalBinding;
  const reviewLoading = externallyLoaded ? authoritativeReview.status === "loading" : loading;
  const reviewMissing = externallyLoaded ? false : missing;

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
      if (externallyLoaded && externalBinding && externalReview) {
        const validated = validatedDecisionResponse(result, externalReview, runId, selectedDecision);
        if (!validated) {
          setInvalidDecisionBinding(externalBinding);
          setError("G02 decision response could not be validated. Refreshing the authoritative review.");
          try { await refreshAuthoritativeState?.(); } catch { /* The panel remains fail-closed until a valid binding arrives. */ }
          return;
        }
        setDecisionOverride({ binding: externalBinding, value: validated });
      } else setReview(result);
      setMissing(false);
    } catch (reason: unknown) {
      setError(reason instanceof ApiClientError && reason.status === 409 ? "G02 is stale. Refresh the authoritative run state before deciding." : "The G02 decision could not be recorded.");
    } finally { setSubmitting(false); }
  }

  const packageData = review?.package;
  const integrity = packageData?.integrity;
  const integrityVerified = Boolean(integrity?.source_read_only_verified && integrity.before_fingerprint === integrity.after_snapshot_fingerprint);
  const approved = review?.status === "approved" || review?.status === "approved_with_comment";
  const rejected = review?.status === "modification_requested" || review?.status === "rejected" || review?.status === "stale";

  return <section className={styles.panel} aria-label="G02 source integrity review">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S1-F08</p><Heading>G02 source-integrity boundary</Heading></div>{review ? <strong>{review.status}</strong> : null}</div>
    {reviewLoading ? <p className={styles.note}>Loading G02 review package</p> : null}
    {externallyLoaded && authoritativeReview.status === "unavailable" ? <div><p role="status" className={styles.note}>G02 review package is unavailable because the response was invalid.</p><button type="button" onClick={authoritativeReview.retry}>Retry G02 review</button></div> : null}
    {externallyLoaded && authoritativeReview.status === "error" ? <div><p role="alert">G02 review package could not be loaded.</p><button type="button" onClick={authoritativeReview.retry}>Retry G02 review</button></div> : null}
    {!reviewLoading && reviewMissing ? <div><p className={styles.note}>G02 is pending. Initialize the review package from the finalized immutable snapshot.</p><button type="button" onClick={initializePackage} disabled={submitting}>Initialize G02 review</button></div> : null}
    {event?.event_type === "SOURCE_INTEGRITY_FAILED" ? <p role="alert">Source integrity failed. Approval is blocked until the source boundary is resolved.</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {packageData ? <>
      <div className={styles.dimensionGrid} aria-label="G02 integrity summary"><div><span>Integrity</span><strong>{integrity?.status ?? "unknown"}</strong></div><div><span>Policy</span><strong>{packageData.policy_version}</strong></div><div><span>State version</span><strong>{review?.state_version}</strong></div><div><span>Boundary</span><strong>{review?.baseline_input_boundary ?? "Not established"}</strong></div></div>
      <dl className={styles.metadataGrid}><div><dt>Source fingerprint</dt><dd>{packageData.source_fingerprint}</dd></div><div><dt>After-snapshot fingerprint</dt><dd>{integrity?.after_snapshot_fingerprint}</dd></div><div><dt>Snapshot fingerprint</dt><dd>{packageData.snapshot_fingerprint}</dd></div><div><dt>Package checksum</dt><dd>{packageData.package_checksum}</dd></div></dl>
      {integrity && integrity.before_fingerprint !== integrity.after_snapshot_fingerprint ? <p role="alert">The original source changed after snapshot creation. This package cannot be approved.</p> : null}
      <Subheading>Immutable evidence</Subheading><ul className={styles.list}>{packageData.artifacts.map((artifact) => <li key={artifact.artifact_id}><a className={styles.actionLink} href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`}>{artifact.relative_path}</a><code>{artifact.checksum}</code></li>)}</ul>
      {approved ? <p className={styles.note}>Baseline input boundary: immutable snapshot {review?.baseline_input_boundary}.</p> : rejected ? <p className={styles.note}>G02 is {review?.status}; the workflow will not continue until a new valid evidence package is created.</p> : decisionValidationBlocked ? <p className={styles.note}>Waiting for the authoritative G02 review after an invalid decision response.</p> : <><p className={styles.note}>{integrityVerified ? "G02 evidence is finalized and verified. Record the approval decision to continue." : "G02 approval is blocked while source-integrity evidence is being finalized or verified."}</p><div className={styles.previewPanel}><label htmlFor="g02-decision">Decision</label><select id="g02-decision" value={selectedDecision} onChange={(e) => setSelectedDecision(e.target.value as G02Decision)}>{decisions.map((decision) => <option key={decision.value} value={decision.value}>{decision.label}</option>)}</select><label htmlFor="g02-comment">Comment</label><textarea id="g02-comment" value={comment} onChange={(e) => setComment(e.target.value)} rows={3} placeholder="Optional rationale; required for approval with comment." /><button type="button" onClick={submitDecision} disabled={submitting || !integrityVerified}>{submitting ? "Recording decision..." : "Record G02 decision"}</button></div></>}
    </> : null}
  </section>;
}
