"use client";

import { useEffect, useState } from "react";
import { ApiClientError } from "@/api/client";
import { getFeasibility } from "@/api/compatibility";
import { getPlan } from "@/api/plans";
import type { ApprovedJourneyRoute, ApprovedJourneyStage } from "@/presentation/runJourney";
import type { FeasibilityResponse } from "@/types/compatibility";
import type { PlanResponse } from "@/types/planning";

export type ApprovedJourneyRouteStatus = "disabled" | "loading" | "ready" | "empty" | "failed";

function majorOfFamily(family: string | undefined): number {
  const match = family?.match(/\d+/);
  return match ? Number(match[0]) : 0;
}

function isNotFound(reason: unknown): boolean {
  return reason instanceof ApiClientError && reason.status === 404;
}

export function buildApprovedJourneyRoute(
  plan: PlanResponse | null,
  feasibility: FeasibilityResponse | null,
): ApprovedJourneyRoute {
  const metadata = new Map(feasibility?.route.map((stage) => [stage.stage_id, stage]) ?? []);
  const routeIds = plan?.plan.route.length
    ? plan.plan.route
    : (feasibility?.route.map((stage) => stage.stage_id) ?? []);
  const stages: ApprovedJourneyStage[] = [];
  let currentMajor = majorOfFamily(plan?.plan.source_family) || majorOfFamily(feasibility?.source_family);
  for (const stageId of routeIds) {
    const stage = metadata.get(stageId);
    const sourceMajor = stage ? majorOfFamily(stage.source_family) : currentMajor;
    const targetMajor = stage ? majorOfFamily(stage.target_family) : Math.max(sourceMajor + 1, currentMajor);
    stages.push({ stageId, sourceMajor, targetMajor });
    currentMajor = targetMajor;
  }
  return stages;
}

export function useApprovedJourneyRoute(runId: string, enabled: boolean, refreshKey: number) {
  const [storedRoute, setStoredRoute] = useState<ApprovedJourneyRoute | null>(null);
  const [routeRunId, setRouteRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<ApprovedJourneyRouteStatus>("disabled");

  useEffect(() => {
    if (!enabled) {
      setStoredRoute(null);
      setRouteRunId(null);
      setStatus("disabled");
      return;
    }
    let active = true;
    setStatus("loading");
    Promise.all([
      getPlan(runId).catch((reason: unknown) => (isNotFound(reason) ? null : Promise.reject(reason))),
      getFeasibility(runId).catch((reason: unknown) => (isNotFound(reason) ? null : Promise.reject(reason))),
    ])
      .then(([plan, feasibility]) => {
        if (!active) return;
        if (plan == null && feasibility == null) {
          setStoredRoute(null);
          setRouteRunId(null);
          setStatus("empty");
          return;
        }
        const stages = buildApprovedJourneyRoute(plan, feasibility);
        setStoredRoute(stages.length > 0 ? stages : null);
        setRouteRunId(stages.length > 0 ? runId : null);
        setStatus(stages.length > 0 ? "ready" : "empty");
      })
      .catch(() => {
        if (active) setStatus("failed");
      });
    return () => { active = false; };
  }, [enabled, refreshKey, runId]);

  const route = routeRunId === runId ? storedRoute : null;
  return { route, status };
}