"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getTransformation } from "@/api/transformation";
import { ApiClientError } from "@/api/client";
import type { TransformationProjection } from "@/types/transformation";

export function useTransformation(runId: string, refreshKey = 0) {
  const [projection, setProjection] = useState<TransformationProjection | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "failed">("loading");
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<ApiClientError | null>(null);
  const loadedRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!loadedRef.current) setStatus("loading");
    try {
      setProjection(await getTransformation(runId));
      loadedRef.current = true;
      setStatus("ready");
      setRefreshError(null);
      setLoadError(null);
    } catch (error) {
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
  }, [runId]);
  useEffect(() => { void refresh(); }, [refresh, refreshKey]);
  return { projection, status, refresh, refreshError, loadError };
}
