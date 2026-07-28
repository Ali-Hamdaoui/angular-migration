"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiClientError } from "@/api/client";
import { decideG06, explainPlan, getPlanReview, revisePlan } from "@/api/planningReview";
import type { G06Decision, PlanReviewChanges, PlanReviewResponse } from "@/types/planning";

export type PlanReviewStatus = "loading" | "empty" | "running" | "success" | "blocked" | "stale" | "reconnecting" | "failure" | "authorization";
type PlanningJobProjection = { status: string; current_step: string; attempt: number; max_attempts: number; retryable?: boolean | null; last_error_code?: string | null; last_error_stage?: string | null; last_error_message?: string | null; correlation_id?: string | null };
const operationKeys = new Map<string, string>();
const operationKey = (runId: string, action: string) => {
  const key = `planning-review-${action}-${runId}`;
  const existing = operationKeys.get(key);
  if (existing) return existing;
  const created = key + "-" + crypto.randomUUID();
  operationKeys.set(key, created);
  return created;
};
const correlationId = (error: unknown) => { try { return JSON.parse(error instanceof ApiClientError ? error.responseBody ?? "{}" : "{}").correlation_id ?? "unavailable"; } catch { return "unavailable"; } };

export function usePlanReview({ runId, stateVersion, workflowEvents, planningJob, connectionStatus, refreshAuthoritativeState }: { runId: string; stateVersion: number; workflowEvents: Array<{ event_type: string; sequence: number }>; planningJob?: PlanningJobProjection | null; connectionStatus: string; refreshAuthoritativeState: () => Promise<unknown> }) {
  const [review, setReview] = useState<PlanReviewResponse | null>(null);
  const [status, setStatus] = useState<PlanReviewStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const latestEvent = [...workflowEvents].reverse().find((event) => ["PLAN_REVISION_CREATED", "APPROVAL_MARKED_STALE", "PLANNING_AGENT_COMPLETED", "G06_CREATED", "G06_APPROVED", "G06_MODIFICATION_REQUESTED", "G06_REJECTED", "G06_STALE"].includes(event.event_type));
  const refresh = useCallback(async () => { setStatus("loading"); setError(null); try { setReview(await getPlanReview(runId)); setStatus("success"); } catch (reason) { if (reason instanceof ApiClientError && reason.status === 404) { setReview(null); if (planningJob?.status === "technical_failed") { setStatus("failure"); setError(`Planning failed before a MigrationPlan was created. Code: ${planningJob.last_error_code ?? "unavailable"}. Stage: ${planningJob.last_error_stage ?? planningJob.current_step}. Attempt: ${planningJob.retryable ? `${planningJob.attempt} of ${planningJob.max_attempts}` : `${planningJob.attempt} (terminal)`}. Retryable: ${planningJob.retryable ? "yes" : "no"}. Correlation ID: ${planningJob.correlation_id ?? "unavailable"}`); } else setStatus("empty"); } else if (reason instanceof ApiClientError && [401, 403].includes(reason.status)) setStatus("authorization"); else if (reason instanceof ApiClientError && reason.status === 409) setStatus("stale"); else { setStatus("failure"); setError(`Plan review could not be loaded. Correlation ID: ${correlationId(reason)}`); } } }, [planningJob, runId]);
  useEffect(() => { void refresh(); }, [refresh, stateVersion, latestEvent?.sequence]);
  useEffect(() => { if (["reconnecting", "recovering"].includes(connectionStatus)) setStatus("reconnecting"); if (connectionStatus === "open") void refresh(); }, [connectionStatus, refresh]);
  const mutate = useCallback(async (action: string, operation: () => Promise<PlanReviewResponse>) => { setLastAction(action); setStatus("running"); setError(null); try { const result = await operation(); setReview(result); setStatus("success"); await refreshAuthoritativeState(); await refresh(); return result; } catch (reason) { if (reason instanceof ApiClientError && reason.status === 409) { setStatus("stale"); await refresh(); await refreshAuthoritativeState(); } else if (reason instanceof ApiClientError && [401, 403].includes(reason.status)) setStatus("authorization"); else { setStatus("failure"); setError(`${action} failed. Correlation ID: ${correlationId(reason)}`); } return null; } }, [refresh, refreshAuthoritativeState]);
  const revise = useCallback((changes: PlanReviewChanges) => { if (!review?.plan || !review.stage_plan || !review.plan_checksum) return Promise.resolve(null); const artifactSetChecksum = review.computed_artifact_set_checksum ?? review.artifact_set_checksum ?? ""; return mutate("Plan revision", () => revisePlan(runId, { expected_state_version: stateVersion, idempotency_key: operationKey(runId, "revision"), plan: review.plan!, stage_plan: review.stage_plan!, changes, artifact_set_checksum: artifactSetChecksum, prerequisite_artifacts: review.artifact_ids.map((artifact_id) => ({ artifact_id, checksum: review.artifact_checksums[artifact_id] })), correlation_id: crypto.randomUUID() })); }, [mutate, review, runId, stateVersion]);
  const explain = useCallback(() => { const plan = review?.plan; if (!plan || !review.stage_plan || !review.plan_checksum) return Promise.resolve(null); const artifactSetChecksum = review.computed_artifact_set_checksum ?? review.artifact_set_checksum ?? ""; return mutate("Planning explanation", () => explainPlan(runId, { expected_state_version: stateVersion, idempotency_key: operationKey(runId, "explanation"), plan, stage_plan: review.stage_plan!, plan_version: Number(plan.version ?? 1), artifact_set_checksum: artifactSetChecksum, prerequisite_artifacts: review.artifact_ids.map((artifact_id) => ({ artifact_id, checksum: review.artifact_checksums[artifact_id] })), correlation_id: crypto.randomUUID() })); }, [mutate, review, runId, stateVersion]);
  const decide = useCallback((decision: G06Decision, comment: string | null) => { if (!review?.plan_checksum || !review.stage_plan_checksum || !review.package_checksum) return Promise.resolve(null); return mutate("G06 decision", () => decideG06(runId, { expected_state_version: stateVersion, idempotency_key: operationKey(runId, "g06"), gate_version: review.gate_version, package_checksum: review.package_checksum, artifact_set_checksum: (review.package?.artifact_set_checksum as string) ?? "", plan_checksum: review.plan_checksum!, stage_plan_checksum: review.stage_plan_checksum!, decision, comment, correlation_id: crypto.randomUUID() })); }, [mutate, review, runId, stateVersion]);
  return { review, status, error, lastAction, refresh, revise, explain, decide };
}
