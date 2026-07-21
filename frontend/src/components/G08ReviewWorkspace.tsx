"use client";

/** Authoritative G08 transformation acceptance workspace. */

import React, { useCallback, useEffect, useState } from "react";
import { ApiClientError, getBackendBaseUrl } from "@/api/client";
import { decideG08, getG08Approval, initializeG08 } from "@/api/transformations";
import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import type { G08Decision, G08ReviewResponse } from "@/types/transformation";
import { StatusPill } from "@/components/StatusPill";

type ViewState =
  | "loading"
  | "empty"
  | "in_progress"
  | "success"
  | "blocked"
  | "stale"
  | "reconnecting"
  | "failure"
  | "authorization";

interface Props {
  runId: string;
  stageId: string;
  gateId: string;
  expectedStateVersion: number;
  connectionStatus?: AuthoritativeConnectionStatus;
  onAuthoritativeRefresh?: () => Promise<void> | void;
  onDecision?: (decision: G08Decision) => void;
}

interface ErrorDetails {
  code?: string;
  message: string;
  correlationId?: string;
}

const DECISIONS: { value: G08Decision; label: string; className: string }[] = [
  { value: "approved", label: "Approve", className: "bg-green-600 hover:bg-green-700" },
  { value: "approved_with_comment", label: "Approve with Comment", className: "bg-blue-600 hover:bg-blue-700" },
  { value: "modification_requested", label: "Request Changes", className: "bg-amber-600 hover:bg-amber-700" },
  { value: "rejected", label: "Reject", className: "bg-red-600 hover:bg-red-700" },
];

function mapReviewState(review: G08ReviewResponse): ViewState {
  if (review.status === "approved" || review.status === "approved_with_comment") return "success";
  if (review.status === "stale") return "stale";
  if (review.status === "rejected" || review.status === "modification_requested") return "blocked";
  return "in_progress";
}

function parseApiError(reason: unknown, fallback: string): ErrorDetails {
  if (!(reason instanceof ApiClientError)) {
    return { message: reason instanceof Error ? reason.message : fallback };
  }
  try {
    const body = JSON.parse(reason.responseBody ?? "{}") as {
      error_code?: string;
      message?: string;
      correlation_id?: string;
    };
    return {
      code: body.error_code,
      message: body.message ?? fallback,
      correlationId: body.correlation_id,
    };
  } catch {
    return { message: fallback };
  }
}

function artifactHref(path: string): string {
  return path.startsWith("http://") || path.startsWith("https://")
    ? path
    : `${getBackendBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

export function G08ReviewWorkspace({
  runId,
  stageId,
  gateId,
  expectedStateVersion,
  connectionStatus = "open",
  onAuthoritativeRefresh,
  onDecision,
}: Props) {
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [review, setReview] = useState<G08ReviewResponse | null>(null);
  const [comment, setComment] = useState("");
  const [pendingDecision, setPendingDecision] = useState<G08Decision | null>(null);
  const [error, setError] = useState<ErrorDetails | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchReview = useCallback(async () => {
    if (connectionStatus === "reconnecting" || connectionStatus === "recovering" || connectionStatus === "connecting") {
      setViewState("reconnecting");
    } else {
      setViewState((current) => current === "loading" ? "loading" : "reconnecting");
    }
    try {
      const result = await getG08Approval(runId, stageId, gateId);
      setReview(result);
      setError(null);
      setViewState(mapReviewState(result));
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setReview(null);
        setError(null);
        setViewState("empty");
        return;
      }
      const parsed = parseApiError(reason, "The G08 review could not be loaded.");
      setError(parsed);
      if (reason instanceof ApiClientError && (reason.status === 401 || reason.status === 403)) {
        setViewState("authorization");
      } else if (reason instanceof ApiClientError && reason.status === 409) {
        setViewState("stale");
      } else {
        setViewState("failure");
      }
    }
  }, [connectionStatus, gateId, runId, stageId]);

  useEffect(() => { void fetchReview(); }, [fetchReview]);

  const refreshAuthoritativeState = async () => {
    if (onAuthoritativeRefresh) await onAuthoritativeRefresh();
  };

  const handleInitialize = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await initializeG08(runId, stageId, gateId, {
        expected_state_version: expectedStateVersion,
        idempotency_key: `g08-init-${crypto.randomUUID()}`,
        gate_id: gateId,
      });
      setReview(result);
      setViewState(mapReviewState(result));
      await refreshAuthoritativeState();
    } catch (reason: unknown) {
      const parsed = parseApiError(reason, "Failed to initialize the G08 review package.");
      setError(parsed);
      if (reason instanceof ApiClientError && (reason.status === 401 || reason.status === 403)) setViewState("authorization");
      else if (reason instanceof ApiClientError && reason.status === 409) setViewState("stale");
      else setViewState("failure");
    } finally {
      setSubmitting(false);
    }
  };

  const submitDecision = async (decision: G08Decision) => {
    if (!review) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await decideG08(runId, stageId, gateId, {
        expected_state_version: review.state_version,
        idempotency_key: `g08-dec-${crypto.randomUUID()}`,
        decision,
        comment: comment.trim() || undefined,
        gate_id: review.gate_id,
        gate_version: review.gate_version,
        package_checksum: review.package_checksum,
        artifact_set_checksum: review.artifact_set_checksum,
        workspace_fingerprint: review.workspace_fingerprint,
        plan_version: review.plan_version,
        plan_checksum: review.plan_checksum,
      });
      setReview(result);
      setViewState(mapReviewState(result));
      setPendingDecision(null);
      setComment("");
      onDecision?.(decision);
      await refreshAuthoritativeState();
    } catch (reason: unknown) {
      const parsed = parseApiError(reason, "Failed to persist the G08 decision.");
      setError(parsed);
      if (reason instanceof ApiClientError && (reason.status === 401 || reason.status === 403)) setViewState("authorization");
      else if (reason instanceof ApiClientError && reason.status === 409) {
        setViewState("stale");
        await refreshAuthoritativeState();
      } else setViewState("failure");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDecision = (decision: G08Decision) => {
    if (decision === "approved_with_comment" || decision === "modification_requested") {
      setPendingDecision(decision);
      return;
    }
    void submitDecision(decision);
  };

  const isDisconnected = connectionStatus === "reconnecting" || connectionStatus === "recovering" || connectionStatus === "connecting";
  const approvalsBlocked = Boolean(review?.technical_blockers.length);
  const statusValue = viewState === "success" ? "PASSED" : viewState === "failure" ? "FAILED" : viewState === "blocked" || viewState === "stale" || viewState === "authorization" ? "BLOCKED" : "RUNNING";

  if (viewState === "loading") {
    return <section className="g08-workspace p-4 border rounded-lg" aria-label="G08 transformation acceptance"><p role="status">Loading G08 review package…</p></section>;
  }

  return (
    <section className="g08-workspace p-4 border rounded-lg space-y-4" aria-label="G08 transformation acceptance">
      <div className="flex items-center justify-between">
        <div><h3 className="text-lg font-semibold">G08 — Transformation Acceptance</h3><p className="text-sm text-gray-500">Backend-authoritative review of the exact transformation evidence set.</p></div>
        <StatusPill value={statusValue} />
      </div>

      {(viewState === "reconnecting" || isDisconnected) && <div role="status" className="p-2 bg-blue-50 border border-blue-200 rounded text-sm">Reconnecting to authoritative run state. Decision controls are disabled.</div>}
      {viewState === "empty" && <div className="p-3 bg-gray-50 rounded"><p>No G08 package exists for this transformation evidence yet.</p></div>}
      {viewState === "authorization" && <div role="alert" className="p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">You are not authorized to inspect or decide this approval gate.</div>}
      {viewState === "failure" && <div role="alert" className="p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">{error?.message ?? "The G08 review failed."}</div>}
      {viewState === "stale" && <div role="alert" className="p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-800">This review is stale because its workspace, plan, state, or artifact binding changed. Refresh the run and generate a new package.</div>}

      {error?.correlationId && <p className="text-xs text-gray-500">Correlation ID: <code>{error.correlationId}</code></p>}
      {error?.code && <p className="text-xs text-gray-500">Error code: <code>{error.code}</code></p>}

      {review && <>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 bg-gray-50 rounded text-sm">
          <div><span className="text-gray-500">Gate version</span><p className="font-mono">{review.gate_version}</p></div>
          <div><span className="text-gray-500">Status</span><p className="font-mono font-bold">{review.status}</p></div>
          <div><span className="text-gray-500">Decision</span><p className="font-mono">{review.decision ?? "—"}</p></div>
          <div><span className="text-gray-500">State version</span><p className="font-mono">{review.state_version}</p></div>
          <div className="col-span-2"><span className="text-gray-500">Package checksum</span><p className="font-mono text-xs break-all">{review.package_checksum}</p></div>
          <div className="col-span-2"><span className="text-gray-500">Workspace fingerprint</span><p className="font-mono text-xs break-all">{review.workspace_fingerprint}</p></div>
        </div>

        <div className="space-y-2 text-sm">
          <h4 className="font-medium">Transformation Summary</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-2 bg-green-50 rounded"><p className="text-gray-500 text-xs">Update status</p><p className="font-mono text-xs">{review.package.transformation_result.update_status ?? "—"}</p></div>
            <div className="p-2 bg-blue-50 rounded"><p className="text-gray-500 text-xs">Target version</p><p className="font-mono text-xs">{review.package.transformation_result.resolved_target_version ?? "—"}</p></div>
            <div className="p-2 bg-amber-50 rounded"><p className="text-gray-500 text-xs">Evidence risk</p><p className="font-mono text-xs">{review.package.evidence_result.overall_risk_level ?? "—"}</p></div>
            <div className="p-2 bg-gray-50 rounded"><p className="text-gray-500 text-xs">Files changed</p><p className="font-mono text-xs">{review.package.evidence_result.total_files_changed ?? "—"}</p></div>
          </div>
        </div>

        <div className="space-y-2 text-sm">
          <h4 className="font-medium">Immutable Evidence</h4>
          <ul className="space-y-2">{review.artifact_ids.map((artifactId) => <li key={artifactId} className="p-2 bg-gray-50 rounded flex flex-col"><a href={artifactHref(review.artifact_links[artifactId] ?? `/api/v1/artifacts/${encodeURIComponent(artifactId)}`)} target="_blank" rel="noreferrer" className="underline">{artifactId}{artifactId === review.package_artifact_id ? " (G08 package)" : ""}</a><code className="text-xs break-all">{review.package.artifact_refs.find((item) => item.artifact_id === artifactId)?.checksum ?? "package checksum-bound"}</code></li>)}</ul>
        </div>

        {review.technical_blockers.length > 0 && <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded"><h4 className="font-medium text-red-800">Technical blockers</h4><ul className="list-disc ml-5 text-sm text-red-700">{review.technical_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></div>}
        {review.comment && <div className="p-2 bg-gray-50 rounded text-sm"><span className="text-gray-500">Decision comment: </span>{review.comment}</div>}
        {review.stale_reason && <div className="p-2 bg-amber-50 rounded text-sm text-amber-800">Stale reason: {review.stale_reason}</div>}
      </>}

      <div className="space-y-3">
        {(viewState === "empty" || viewState === "stale") && <button onClick={() => void handleInitialize()} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50" disabled={submitting || isDisconnected}>{viewState === "stale" ? "Generate Current Review Package" : "Initialize Review Package"}</button>}

        {review && viewState === "in_progress" && <div className="flex flex-wrap gap-2">{DECISIONS.map((item) => {
          const isApproval = item.value === "approved" || item.value === "approved_with_comment";
          return <button key={item.value} onClick={() => handleDecision(item.value)} className={`px-4 py-2 text-white rounded text-sm ${item.className} disabled:opacity-50`} disabled={submitting || isDisconnected || (isApproval && approvalsBlocked)}>{item.label}</button>;
        })}</div>}

        {pendingDecision && <div className="space-y-2 p-3 bg-gray-50 rounded"><label htmlFor="g08-comment" className="font-medium text-sm">Decision comment</label><textarea id="g08-comment" value={comment} onChange={(event) => setComment(event.target.value)} placeholder={pendingDecision === "modification_requested" ? "Describe the required transformation changes…" : "Explain the approval conditions…"} className="w-full p-2 border rounded text-sm min-h-[80px]" rows={3} /><div className="flex gap-2"><button onClick={() => void submitDecision(pendingDecision)} className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm disabled:opacity-50" disabled={!comment.trim() || submitting || isDisconnected}>Submit {pendingDecision === "modification_requested" ? "Change Request" : "Approval"}</button><button onClick={() => { setPendingDecision(null); setComment(""); }} className="px-3 py-1.5 bg-gray-300 text-gray-700 rounded text-sm">Cancel</button></div></div>}
      </div>
    </section>
  );
}
