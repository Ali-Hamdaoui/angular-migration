"use client";

/**
 * G08ReviewWorkspace — Transformation review workspace combining diff viewer, risk summary,
 * comments, decision controls, stale warning, and failure/blocked states.
 */

import React, { useCallback, useEffect, useState } from "react";
import { decideG08, getG08Approval, initializeG08 } from "@/api/transformations";
import type { G08Decision, G08ReviewResponse } from "@/types/transformation";
import { StatusPill } from "@/components/StatusPill";

type ViewState = "loading" | "empty" | "success" | "blocked" | "stale" | "reconnecting" | "failure";

interface Props {
  runId: string;
  stageId: string;
  gateId: string;
  expectedStateVersion: number;
  onDecision?: (decision: G08Decision) => void;
}

const DECISIONS: { value: G08Decision; label: string; variant: string }[] = [
  { value: "approved", label: "Approve", variant: "bg-green-600 hover:bg-green-700" },
  { value: "approved_with_comment", label: "Approve with Comment", variant: "bg-blue-600 hover:bg-blue-700" },
  { value: "modification_requested", label: "Request Changes", variant: "bg-amber-600 hover:bg-amber-700" },
  { value: "rejected", label: "Reject", variant: "bg-red-600 hover:bg-red-700" },
];

export function G08ReviewWorkspace({
  runId,
  stageId,
  gateId,
  expectedStateVersion,
  onDecision,
}: Props) {
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [review, setReview] = useState<G08ReviewResponse | null>(null);
  const [comment, setComment] = useState("");
  const [showCommentInput, setShowCommentInput] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchReview = useCallback(async () => {
    try {
      setViewState("reconnecting");
      const result = await getG08Approval(runId, stageId, gateId);
      setReview(result);
      if (result.status === "approved" || result.status === "approved_with_comment") {
        setViewState("success");
      } else if (result.status === "rejected" || result.status === "modification_requested") {
        setViewState("blocked");
      } else if (result.status === "stale") {
        setViewState("stale");
      } else {
        setViewState("empty");
      }
    } catch {
      setViewState("empty");
    }
  }, [runId, stageId, gateId]);

  useEffect(() => {
    fetchReview();
  }, [fetchReview]);

  const handleInitialize = async () => {
    const idempotencyKey = `g08-init-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      const result = await initializeG08(runId, stageId, gateId, {
        expected_state_version: expectedStateVersion,
        idempotency_key: idempotencyKey,
        actor: "operator",
        decision: "approved",
        gate_id: gateId,
      });
      setReview(result);
      setViewState("empty");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to initialize review");
      setViewState("failure");
    }
  };

  const handleDecision = async (decision: G08Decision) => {
    if (decision === "approved_with_comment" || decision === "modification_requested") {
      setShowCommentInput(true);
      return;
    }
    await submitDecision(decision);
  };

  const handleCommentSubmit = async (decision: G08Decision) => {
    if (!comment.trim()) return;
    await submitDecision(decision);
  };

  const submitDecision = async (decision: G08Decision) => {
    const idempotencyKey = `g08-dec-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setSubmitting(true);
    try {
      const result = await decideG08(runId, stageId, gateId, {
        expected_state_version: expectedStateVersion,
        idempotency_key: idempotencyKey,
        actor: "operator",
        decision,
        comment: comment || undefined,
        gate_id: gateId,
      });
      setReview(result);
      if (result.status === "approved" || result.status === "approved_with_comment") {
        setViewState("success");
      } else {
        setViewState("blocked");
      }
      onDecision?.(decision);
      setShowCommentInput(false);
      setComment("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to record decision");
    } finally {
      setSubmitting(false);
    }
  };

  if (viewState === "loading") {
    return (
      <div className="g08-workspace p-4 border rounded-lg">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-gray-200 rounded w-1/3" />
          <div className="h-8 bg-gray-200 rounded w-full" />
          <div className="h-4 bg-gray-200 rounded w-2/3" />
        </div>
      </div>
    );
  }

  return (
    <div className="g08-workspace p-4 border rounded-lg space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">G08 — Transformation Acceptance</h3>
        <StatusPill
          status={
            viewState === "success" ? "PASSED"
            : viewState === "stale" ? "BLOCKED"
            : viewState === "failure" ? "FAILED"
            : viewState === "blocked" ? "BLOCKED"
            : "RUNNING"
          }
        />
      </div>

      {/* Package info */}
      {review && (
        <div className="grid grid-cols-2 gap-3 p-3 bg-gray-50 rounded text-sm">
          <div>
            <span className="text-gray-500">Gate version</span>
            <p className="font-mono">{review.gate_version}</p>
          </div>
          <div>
            <span className="text-gray-500">Status</span>
            <p className="font-mono font-bold">{review.status}</p>
          </div>
          <div>
            <span className="text-gray-500">Decision</span>
            <p className="font-mono">{review.decision || "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">Package checksum</span>
            <p className="font-mono text-xs truncate">{review.package_checksum.slice(0, 24)}…</p>
          </div>
        </div>
      )}

      {/* Evidence summary from package */}
      {review?.package && (
        <div className="space-y-2 text-sm">
          <h4 className="font-medium">Transformation Summary</h4>
          <div className="grid grid-cols-3 gap-3">
            <div className="p-2 bg-green-50 rounded">
              <p className="text-gray-500 text-xs">Update status</p>
              <p className="font-mono text-xs">
                {(review.package.transformation_result as Record<string, unknown>)?.update_status as string ?? "—"}
              </p>
            </div>
            <div className="p-2 bg-blue-50 rounded">
              <p className="text-gray-500 text-xs">Target version</p>
              <p className="font-mono text-xs">
                {(review.package.transformation_result as Record<string, unknown>)?.resolved_target_version as string ?? "—"}
              </p>
            </div>
            <div className="p-2 bg-amber-50 rounded">
              <p className="text-gray-500 text-xs">Evidence risk</p>
              <p className="font-mono text-xs">
                {(review.package.evidence_result as Record<string, unknown>)?.overall_risk_level as string ?? "—"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="space-y-3">
        {(viewState === "empty" || viewState === "stale") && (
          <button
            onClick={handleInitialize}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            disabled={submitting}
          >
            Initialize Review Package
          </button>
        )}

        {viewState === "empty" && (
          <div className="flex flex-wrap gap-2">
            {DECISIONS.map((d) => (
              <button
                key={d.value}
                onClick={() => handleDecision(d.value)}
                className={`px-4 py-2 text-white rounded text-sm ${d.variant} disabled:opacity-50`}
                disabled={submitting}
              >
                {d.label}
              </button>
            ))}
          </div>
        )}

        {showCommentInput && (
          <div className="space-y-2 p-3 bg-gray-50 rounded">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Enter your comment..."
              className="w-full p-2 border rounded text-sm min-h-[80px]"
              rows={3}
            />
            <div className="flex gap-2">
              <button
                onClick={() => handleCommentSubmit("approved_with_comment")}
                className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
                disabled={!comment.trim() || submitting}
              >
                Submit
              </button>
              <button
                onClick={() => setShowCommentInput(false)}
                className="px-3 py-1.5 bg-gray-300 text-gray-700 rounded text-sm hover:bg-gray-400"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Stale warning */}
      {viewState === "stale" && (
        <div className="p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700">
          This review is stale. Evidence or workspace fingerprint has changed. Please re-initialize.
        </div>
      )}

      {viewState === "failure" && (
        <div className="p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error || "An error occurred"}
        </div>
      )}

      {/* Comment display */}
      {review?.comment && (
        <div className="p-2 bg-gray-50 rounded text-sm">
          <span className="text-gray-500">Comment: </span>
          {review.comment}
        </div>
      )}

      {review?.stale_reason && (
        <div className="p-2 bg-amber-50 rounded text-sm text-amber-700">
          Stale reason: {review.stale_reason}
        </div>
      )}
    </div>
  );
}
