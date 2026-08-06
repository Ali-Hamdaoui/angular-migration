"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listCommandExecutions } from "@/api/commands";
import { getTransformation } from "@/api/transformation";
import { ApiClientError } from "@/api/client";
import type { TransformationProjection } from "@/types/transformation";
import type { CommandExecutionResponseDto } from "@/types/generated/api";

export function useTransformation(runId: string, refreshKey = 0) {
  const [projection, setProjection] = useState<TransformationProjection | null>(null);
  const [executions, setExecutions] = useState<CommandExecutionResponseDto[]>([]);
  const [executionStatus, setExecutionStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "failed">("loading");
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<ApiClientError | null>(null);
  const loadedRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!loadedRef.current) setStatus("loading");
    const [projectionResult, executionResult] = await Promise.allSettled([
      getTransformation(runId),
      listCommandExecutions(runId),
    ]);
    if (projectionResult.status === "fulfilled") {
      setProjection(projectionResult.value);
      loadedRef.current = true;
      setStatus("ready");
      setRefreshError(null);
      setLoadError(null);
    } else {
      const error = projectionResult.reason;
      if (!loadedRef.current) {
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
  }, [runId]);
  useEffect(() => { void refresh(); }, [refresh, refreshKey]);
  return { projection, executions, executionStatus, status, refresh, refreshError, loadError };
}
