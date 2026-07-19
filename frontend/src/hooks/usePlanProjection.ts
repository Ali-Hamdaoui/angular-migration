"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { createPlan, getPlan } from "@/api/plans";
import type { PlanCreateRequest, PlanResponse } from "@/types/planning";

export type PlanProjectionStatus = "loading" | "empty" | "running" | "success" | "blocked" | "stale" | "reconnecting" | "failure" | "authorization";

function correlationFrom(error: ApiClientError) {
  try { return (JSON.parse(error.responseBody ?? "{}") as { correlation_id?: string }).correlation_id ?? "unavailable"; } catch { return "unavailable"; }
}

function operationKey(runId: string) { return `plan-${runId}-${Date.now()}`; }

export function usePlanProjection({ runId, stateVersion, workflowEvents, connectionStatus, refreshAuthoritativeState }: { runId: string; stateVersion: number; workflowEvents: Array<{ event_type: string; sequence: number }>; connectionStatus: string; refreshAuthoritativeState?: () => Promise<unknown> }) {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [status, setStatus] = useState<PlanProjectionStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const latestPlanEvent = useMemo(() => [...workflowEvents].reverse().find((event) => event.event_type === "MIGRATION_PLAN_CREATED" || event.event_type === "STAGE_PLAN_CREATED"), [workflowEvents]);

  const refresh = useCallback(async () => {
    setStatus((current) => current === "running" ? current : "loading");
    setError(null);
    try {
      setPlan(await getPlan(runId));
      setStatus("success");
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) { setPlan(null); setStatus("empty"); }
      else if (reason instanceof ApiClientError && reason.status === 403) setStatus("authorization");
      else if (reason instanceof ApiClientError && reason.status === 409) setStatus("blocked");
      else { setStatus("failure"); setError(`Plan could not be loaded. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`); }
    }
  }, [runId]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion, latestPlanEvent?.sequence]);
  useEffect(() => {
    if (connectionStatus === "reconnecting" || connectionStatus === "recovering") setStatus("reconnecting");
    if (connectionStatus === "open" && latestPlanEvent) void refresh();
  }, [connectionStatus, latestPlanEvent, refresh]);

  const generate = useCallback(async (input: Omit<PlanCreateRequest, "expected_state_version" | "idempotency_key" | "prerequisite_artifacts"> & { prerequisite_artifacts: PlanCreateRequest["prerequisite_artifacts"] }) => {
    setStatus("running"); setError(null);
    try {
      const result = await createPlan(runId, { ...input, expected_state_version: stateVersion, idempotency_key: operationKey(runId) });
      setPlan(result); setStatus("success");
      await refreshAuthoritativeState?.();
      return result;
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) { await refresh(); setStatus("stale"); await refreshAuthoritativeState?.(); }
      else if (reason instanceof ApiClientError && reason.status === 403) setStatus("authorization");
      else { setStatus("failure"); setError(`Plan generation failed. Correlation ID: ${reason instanceof ApiClientError ? correlationFrom(reason) : "unavailable"}`); }
      return null;
    }
  }, [runId, stateVersion, refresh, refreshAuthoritativeState]);

  return { plan, status, error, refresh, generate };
}
