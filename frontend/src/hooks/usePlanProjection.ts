"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getPlan } from "@/api/plans";
import type { PlanResponse } from "@/types/planning";
import type { PlanningJobProjectionDto } from "@/types/generated/api";

export type PlanProjectionStatus = "loading" | "empty" | "queued" | "resolving_feasibility" | "waiting_g05" | "generating_plan" | "running_planning_review" | "waiting_retry" | "technical_failed" | "completed_blocked" | "waiting_g06" | "completed" | "success" | "blocked" | "reconnecting" | "failure" | "authorization";

function correlationFrom(error: ApiClientError) {
  try { return (JSON.parse(error.responseBody ?? "{}") as { correlation_id?: string }).correlation_id ?? "unavailable"; } catch { return "unavailable"; }
}

function projectJobStatus(job?: Pick<PlanningJobProjectionDto, "status"> | null): PlanProjectionStatus {
  if (!job) return "empty";
  return job.status === "queued_after_g04" ? "queued" : job.status as PlanProjectionStatus;
}

const PLAN_EVENTS = ["MIGRATION_PLAN_CREATED", "STAGE_PLAN_CREATED", "PLANNING_INPUT_RESOLUTION_FAILED", "PLANNING_RETRY_SCHEDULED", "PLANNING_FAILED", "G06_CREATED", "G06_APPROVED"];

export function usePlanProjection({ runId, stateVersion, planningJob, workflowEvents, connectionStatus }: { runId: string; stateVersion: number; planningJob?: PlanningJobProjectionDto | null; workflowEvents: Array<{ event_type: string; sequence: number }>; connectionStatus: string; refreshAuthoritativeState?: () => Promise<unknown> }) {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [status, setStatus] = useState<PlanProjectionStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const latestPlanEvent = useMemo(() => [...workflowEvents].reverse().find((event) => PLAN_EVENTS.includes(event.event_type)), [workflowEvents]);

  const refresh = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      setPlan(await getPlan(runId));
      setStatus("success");
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setPlan(null);
        const projected = projectJobStatus(planningJob);
        if (projected === "waiting_g06" || projected === "completed") {
          setStatus("failure");
          setError(`The planning job is ${planningJob?.status}, but the authoritative MigrationPlan is missing. Correlation ID: ${planningJob?.correlation_id ?? "unavailable"}`);
        } else {
          setStatus(projected);
        }
      } else if (reason instanceof ApiClientError && reason.status === 403) {
        setStatus("authorization");
      } else if (reason instanceof ApiClientError && reason.status === 409) {
        setStatus("blocked");
      } else {
        setStatus("failure");
        setError(`Plan could not be loaded. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`);
      }
    }
  }, [runId, planningJob]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion, latestPlanEvent?.sequence]);
  useEffect(() => {
    if (connectionStatus === "reconnecting" || connectionStatus === "recovering") setStatus("reconnecting");
    if (connectionStatus === "open") void refresh();
  }, [connectionStatus, refresh]);

  return { plan, status, error, refresh };
}
