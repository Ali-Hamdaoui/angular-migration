"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import { decideG06, explainPlan, getPlanReview, revisePlan } from "@/api/planningReview";
import { createLogicalOperationKeys } from "@/lib/idempotency";
import type { G06Decision, PlanReviewChanges, PlanReviewResponse } from "@/types/planning";
import type { PlanningJobProjectionDto } from "@/types/generated/api";

export type PlanReviewStatus = "loading" | "empty" | "running" | "success" | "blocked" | "stale" | "reconnecting" | "failure" | "authorization";
const REVIEW_EVENTS = ["PLAN_REVISION_CREATED", "APPROVAL_MARKED_STALE", "PLANNING_AGENT_COMPLETED", "PLANNING_FAILED", "PLANNING_RETRY_SCHEDULED", "G06_CREATED", "G06_APPROVED", "G06_MODIFICATION_REQUESTED", "G06_REJECTED", "G06_STALE"];
const correlationId = (error: unknown) => { try { return JSON.parse(error instanceof ApiClientError ? error.responseBody ?? "{}" : "{}").correlation_id ?? "unavailable"; } catch { return "unavailable"; } };

function workspaceFingerprint(review: PlanReviewResponse) {
  const stage = review.stage_plan;
  return stage && typeof stage.input_workspace_fingerprint === "string" ? stage.input_workspace_fingerprint : null;
}

function prerequisiteArtifacts(review: PlanReviewResponse) {
  if (!review.artifact_ids.length) return null;
  const artifacts = review.artifact_ids.map((artifact_id) => ({ artifact_id, checksum: review.artifact_checksums[artifact_id] }));
  return artifacts.every((artifact) => Boolean(artifact.checksum)) ? artifacts : null;
}

export function usePlanReview({ runId, stateVersion, workflowEvents, planningJob, connectionStatus, refreshAuthoritativeState }: { runId: string; stateVersion: number; workflowEvents: Array<{ event_type: string; sequence: number }>; planningJob?: PlanningJobProjectionDto | null; connectionStatus: string; refreshAuthoritativeState: () => Promise<unknown> }) {
  const [review, setReview] = useState<PlanReviewResponse | null>(null);
  const [status, setStatus] = useState<PlanReviewStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const operationKeys = useRef(createLogicalOperationKeys(`planning-review-${runId}`));
  const latestEvent = [...workflowEvents].reverse().find((event) => REVIEW_EVENTS.includes(event.event_type));

  const refresh = useCallback(async () => {
    setStatus("loading"); setError(null);
    try { setReview(await getPlanReview(runId)); setStatus("success"); }
    catch (reason) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setReview(null);
        if (planningJob?.status === "technical_failed") {
          setStatus("failure");
          setError(`Planning failed before G06 became available. Code: ${planningJob.last_error_code ?? "unavailable"}. Stage: ${planningJob.last_error_stage ?? planningJob.current_step}. Attempt: ${planningJob.attempt} of ${planningJob.max_attempts}. Correlation ID: ${planningJob.correlation_id ?? "unavailable"}`);
        } else if (planningJob?.status === "waiting_g06" || planningJob?.status === "completed") {
          setStatus("failure");
          setError(`The planning job is ${planningJob.status}, but the authoritative G06 review package is missing. Correlation ID: ${planningJob.correlation_id ?? "unavailable"}`);
        } else setStatus("empty");
      } else if (reason instanceof ApiClientError && [401, 403].includes(reason.status)) setStatus("authorization");
      else if (reason instanceof ApiClientError && reason.status === 409) setStatus("stale");
      else { setStatus("failure"); setError(`Plan review could not be loaded. Correlation ID: ${correlationId(reason)}`); }
    }
  }, [planningJob, runId]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion, latestEvent?.sequence]);
  useEffect(() => { if (["reconnecting", "recovering"].includes(connectionStatus)) setStatus("reconnecting"); if (connectionStatus === "open") void refresh(); }, [connectionStatus, refresh]);

  const mutateReview = useCallback(async (action: string, operation: () => Promise<PlanReviewResponse>) => {
    setLastAction(action); setStatus("running"); setError(null);
    try {
      const result = await operation();
      operationKeys.current.complete(action); operationKeys.current.complete(`${action}-correlation`);
      setReview(result); setStatus("success"); await refreshAuthoritativeState(); await refresh(); return result;
    } catch (reason) {
      if (reason instanceof ApiClientError && reason.status === 409) { operationKeys.current.complete(action); operationKeys.current.complete(`${action}-correlation`); setStatus("stale"); await refreshAuthoritativeState(); await refresh(); }
      else if (reason instanceof ApiClientError && [401, 403].includes(reason.status)) setStatus("authorization");
      else { setStatus("failure"); setError(`${action} failed. Correlation ID: ${correlationId(reason)}`); }
      return null;
    }
  }, [refresh, refreshAuthoritativeState]);

  const revise = useCallback((changes: PlanReviewChanges) => {
    if (!review?.plan || !review.stage_plan || !review.plan_checksum) return Promise.resolve(null);
    const action = "revision";
    const artifactSetChecksum = review.computed_artifact_set_checksum ?? review.artifact_set_checksum ?? "";
    const artifacts = prerequisiteArtifacts(review);
    if (!artifactSetChecksum || !artifacts) return Promise.resolve(null);
    return mutateReview(action, () => revisePlan(runId, { expected_state_version: review.state_version, idempotency_key: operationKeys.current.get(action), plan: review.plan!, stage_plan: review.stage_plan!, changes, artifact_set_checksum: artifactSetChecksum, prerequisite_artifacts: artifacts, workspace_fingerprint: workspaceFingerprint(review), correlation_id: operationKeys.current.get(`${action}-correlation`) }));
  }, [mutateReview, review, runId]);

  const explain = useCallback(() => {
    const plan = review?.plan;
    if (!plan || !review.stage_plan || !review.plan_checksum) return Promise.resolve(null);
    const action = "explanation";
    const artifactSetChecksum = review.computed_artifact_set_checksum ?? review.artifact_set_checksum ?? "";
    const artifacts = prerequisiteArtifacts(review);
    if (!artifactSetChecksum || !artifacts) return Promise.resolve(null);
    return mutateReview(action, () => explainPlan(runId, { expected_state_version: review.state_version, idempotency_key: operationKeys.current.get(action), plan, stage_plan: review.stage_plan!, plan_version: Number(plan.version ?? 1), artifact_set_checksum: artifactSetChecksum, prerequisite_artifacts: artifacts, workspace_fingerprint: workspaceFingerprint(review), correlation_id: operationKeys.current.get(`${action}-correlation`) }));
  }, [mutateReview, review, runId]);

  const decide = useCallback(async (decision: G06Decision, comment: string | null) => {
    if (!review?.plan_checksum || !review.stage_plan_checksum || !review.package_checksum) return null;
    const artifactSetChecksum = review.computed_artifact_set_checksum ?? review.artifact_set_checksum ?? "";
    const artifacts = prerequisiteArtifacts(review);
    if (!artifactSetChecksum || !artifacts) return null;
    const action = `g06-${review.gate_version}-${decision}`;
    setLastAction("G06 decision"); setStatus("running"); setError(null);
    try {
      const result = await decideG06(runId, { expected_state_version: review.state_version, idempotency_key: operationKeys.current.get(action), gate_version: review.gate_version, package_checksum: review.package_checksum, artifact_set_checksum: artifactSetChecksum, plan_checksum: review.plan_checksum, stage_plan_checksum: review.stage_plan_checksum, workspace_fingerprint: workspaceFingerprint(review), decision, comment, correlation_id: operationKeys.current.get(`${action}-correlation`) });
      operationKeys.current.complete(action); operationKeys.current.complete(`${action}-correlation`);
      setReview((current) => current ? { ...current, gate_status: result.status, gate_decision: result.decision, package_checksum: result.package_checksum, artifact_set_checksum: result.artifact_set_checksum, plan_checksum: result.plan_checksum, stage_plan_checksum: result.stage_plan_checksum, state_version: result.state_version, event_sequence: result.event_sequence, idempotent_replay: result.idempotent_replay } : current);
      setStatus("success"); await refreshAuthoritativeState(); await refresh(); return result;
    } catch (reason) {
      if (reason instanceof ApiClientError && reason.status === 409) { operationKeys.current.complete(action); operationKeys.current.complete(`${action}-correlation`); setStatus("stale"); await refreshAuthoritativeState(); await refresh(); }
      else if (reason instanceof ApiClientError && [401, 403].includes(reason.status)) setStatus("authorization");
      else { setStatus("failure"); setError(`G06 decision failed. Correlation ID: ${correlationId(reason)}`); }
      return null;
    }
  }, [refresh, refreshAuthoritativeState, review, runId]);

  return { review, status, error, lastAction, refresh, revise, explain, decide };
}
