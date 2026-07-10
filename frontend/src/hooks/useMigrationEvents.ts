"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getBackendBaseUrl } from "@/api/client";
import type { MigrationEventDto, WorkflowEventType } from "@/types/generated/api";

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface UseMigrationEventsResult {
  status: ConnectionStatus;
  events: MigrationEventDto[];
}

const WORKFLOW_EVENT_TYPES: WorkflowEventType[] = [
  "run_state_changed",
  "stage_state_changed",
  "agent_state_changed",
  "validation_gate_changed",
  "artifact_created",
  "approval_required",
  "workflow_completed",
];

export type EventSourceConstructor = typeof EventSource;

export function useMigrationEvents(
  runId: string,
  createEventSource: EventSourceConstructor = EventSource,
): UseMigrationEventsResult {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [events, setEvents] = useState<MigrationEventDto[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  const handleEvent = useCallback((type: WorkflowEventType) => {
    return (raw: MessageEvent) => {
      const data = JSON.parse(raw.data) as MigrationEventDto;
      setEvents((prev) => [...prev, data]);
    };
  }, []);

  useEffect(() => {
    const url = `${getBackendBaseUrl()}/migrations/${runId}/events`;
    const source = createEventSource(url);
    sourceRef.current = source;

    source.onopen = () => setStatus("open");
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        setStatus("closed");
      } else {
        setStatus("reconnecting");
      }
    };

    for (const type of WORKFLOW_EVENT_TYPES) {
      source.addEventListener(type, handleEvent(type) as EventListener);
    }

    return () => {
      for (const type of WORKFLOW_EVENT_TYPES) {
        source.removeEventListener(type, handleEvent(type) as EventListener);
      }
      source.close();
      sourceRef.current = null;
    };
  }, [runId, createEventSource, handleEvent]);

  return { status, events };
}
