"use client";

import { useCallback, useEffect, useState } from "react";
import { getBackendBaseUrl } from "@/api/client";
import { getAuthoritativeRunState } from "@/api/runs";
import type { AuthoritativeRunStateDto, WorkflowEventDto } from "@/types/generated/api";

export type AuthoritativeConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";

const EVENT_TYPES = ["RUN_CREATED", "RUN_START_ACCEPTED", "RUN_STARTED", "RUN_START_REJECTED", "RUN_RECONSTRUCTED"] as const;

export function useAuthoritativeRun(runId: string, initialState: AuthoritativeRunStateDto) {
  const [state, setState] = useState(initialState);
  const [status, setStatus] = useState<AuthoritativeConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setStatus("recovering");
    return getAuthoritativeRunState(runId)
      .then((next) => {
        setState((current) => ({
          ...next,
          workflow_events: [...next.workflow_events].sort((a, b) => a.sequence - b.sequence),
        }));
        setError(null);
        setStatus("open");
      })
      .catch(() => {
        setError("The authoritative run state could not be refreshed.");
        setStatus("failed");
      });
  }, [runId]);

  useEffect(() => {
    let active = true;
    const source = new EventSource(`${getBackendBaseUrl()}/api/v1/runs/${encodeURIComponent(runId)}/events`);
    const onEvent = (event: MessageEvent) => {
      try {
        const next = JSON.parse(event.data) as WorkflowEventDto;
        setState((current) => {
          if (current.workflow_events.some((item) => item.event_id === next.event_id)) return current;
          return { ...current, workflow_events: [...current.workflow_events, next].sort((a, b) => a.sequence - b.sequence), updated_at: next.occurred_at };
        });
      } catch {
        setError("The backend sent an invalid run event.");
      }
    };
    source.onopen = () => setStatus("open");
    source.onerror = () => {
      if (active) setStatus(source.readyState === EventSource.CLOSED ? "reconnecting" : "recovering");
    };
    for (const type of EVENT_TYPES) source.addEventListener(type, onEvent);
    const interval = window.setInterval(() => { void refresh(); }, 5000);
    void refresh();
    return () => {
      active = false;
      window.clearInterval(interval);
      for (const type of EVENT_TYPES) source.removeEventListener(type, onEvent);
      source.close();
    };
  }, [refresh, runId]);

  return { state, status, error, refresh };
}
