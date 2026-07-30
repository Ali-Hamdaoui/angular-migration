"use client";

import { useCallback, useEffect, useState } from "react";
import { getTransformation } from "@/api/transformation";
import type { TransformationProjection } from "@/types/transformation";

export function useTransformation(runId: string, refreshKey = 0) {
  const [projection, setProjection] = useState<TransformationProjection | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "failed">("loading");
  const refresh = useCallback(async () => {
    setStatus("loading");
    try {
      setProjection(await getTransformation(runId));
      setStatus("ready");
    } catch (error) {
      setProjection(null);
      setStatus(error instanceof Error && error.message.includes("(404)") ? "empty" : "failed");
    }
  }, [runId]);
  useEffect(() => { void refresh(); }, [refresh, refreshKey]);
  return { projection, status, refresh };
}
