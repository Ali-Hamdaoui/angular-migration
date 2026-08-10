"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listCommandExecutions } from "@/api/commands";
import { getTransformation } from "@/api/transformation";
import { ApiClientError } from "@/api/client";
import type { TransformationProjection } from "@/types/transformation";
import type { CommandExecutionResponseDto } from "@/types/generated/api";

export type UseTransformationOptions = {
  enabled: boolean;
  refreshKey?: number;
};

export function useTransformation(
  runId: string,
  { enabled, refreshKey = 0 }: UseTransformationOptions,
) {
  const [projection, setProjection] = useState<TransformationProjection | null>(null);
  const [executions, setExecutions] = useState<CommandExecutionResponseDto[]>([]);
  const [executionStatus, setExecutionStatus] = useState<"idle" | "loading" | "ready" | "unavailable">(
    enabled ? "loading" : "idle",
  );
  const [status, setStatus] = useState<"disabled" | "loading" | "ready" | "empty" | "failed">(
    enabled ? "loading" : "disabled",
  );
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<ApiClientError | null>(null);
  const loadedRunIdRef = useRef<string | null>(null);
  const requestGenerationRef = useRef(0);
  const previousRunIdRef = useRef(runId);

  const refresh = useCallback(async () => {
    if (!enabled) return;

    const generation = ++requestGenerationRef.current;
    const hasConfirmedProjection = loadedRunIdRef.current === runId;
    if (!hasConfirmedProjection) setStatus("loading");
    setExecutionStatus("loading");
    const [projectionResult, executionResult] = await Promise.allSettled([
      getTransformation(runId),
      listCommandExecutions(runId),
    ]);
    if (generation !== requestGenerationRef.current) return;

    if (projectionResult.status === "fulfilled") {
      setProjection(projectionResult.value);
      loadedRunIdRef.current = runId;
      setStatus("ready");
      setRefreshError(null);
      setLoadError(null);
    } else {
      const error = projectionResult.reason;
      if (!hasConfirmedProjection) {
        setProjection(null);
        setStatus(error instanceof ApiClientError && error.status === 404 ? "empty" : "failed");
        setLoadError(error instanceof ApiClientError ? error : null);
      } else {
        setRefreshError(
          error instanceof ApiClientError && error.status === 404
            ? "Transformer state is no longer available."
          : "Background refresh failed; showing the last authoritative state.",
        );
      }
    }
    if (executionResult.status === "fulfilled") {
      setExecutions(executionResult.value.executions);
      setExecutionStatus("ready");
    } else {
      setExecutionStatus("unavailable");
    }
  }, [enabled, runId]);

  useEffect(() => {
    const runChanged = previousRunIdRef.current !== runId;
    if (runChanged) {
      previousRunIdRef.current = runId;
      loadedRunIdRef.current = null;
      setProjection(null);
      setExecutions([]);
      setRefreshError(null);
      setLoadError(null);
    }

    if (!enabled) {
      requestGenerationRef.current += 1;
      setStatus("disabled");
      setExecutionStatus("idle");
      return;
    }

    if (loadedRunIdRef.current === runId) setStatus("ready");
    void refresh();
    return () => {
      requestGenerationRef.current += 1;
    };
  }, [enabled, refresh, refreshKey, runId]);

  return { projection, executions, executionStatus, status, refresh, refreshError, loadError };
}
