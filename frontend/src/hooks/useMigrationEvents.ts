"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getBackendBaseUrl } from "@/api/client";
import type { MigrationEventDto, WorkflowEventType } from "@/types/generated/api";

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "recovering" | "closed";

export interface UseMigrationEventsResult {
  status: ConnectionStatus;
  events: MigrationEventDto[];
  lastSequence: number;
  recoveryRequired: boolean;
  clearRecoveryRequired: () => void;
}

const WORKFLOW_EVENT_TYPES: WorkflowEventType[] = [
  "STATE_CONTRACT_MIGRATED",
  "APPROVAL_POLICY_DISABLED_FOR_PRODUCTION",
  "run_state_changed",
  "stage_state_changed",
  "agent_state_changed",
  "validation_gate_changed",
  "artifact_created",
  "approval_required",
  "workflow_completed",
  "SNAPSHOT_STARTED",
  "SNAPSHOT_CREATED",
  "SNAPSHOT_FAILED",
];

const MAX_LIVE_EVENTS = 200;

export type EventSourceConstructor = typeof EventSource;

export function useMigrationEvents(
  runId: string,
  createEventSource: EventSourceConstructor = EventSource,
): UseMigrationEventsResult {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [events, setEvents] = useState<MigrationEventDto[]>([]);
  const [lastSequence, setLastSequence] = useState(0);
  const [recoveryRequired, setRecoveryRequired] = useState(false);
  const lastSequenceRef = useRef(0);
  const seenEventIdsRef = useRef(new Set<string>());

  const markRecoveryRequired = useCallback(() => {
    setRecoveryRequired(true);
    setStatus("recovering");
  }, []);

  const clearRecoveryRequired = useCallback(() => {
    setRecoveryRequired(false);
    setStatus((current) => (current === "recovering" ? "open" : current));
  }, []);

  const handleEvent = useCallback((raw: MessageEvent) => {
    const data = JSON.parse(raw.data) as MigrationEventDto;
    const previousSequence = lastSequenceRef.current;
    if (seenEventIdsRef.current.has(data.event_id) || data.sequence <= previousSequence) return;
    if (data.sequence > previousSequence + 1) {
      markRecoveryRequired();
      return;
    }
    seenEventIdsRef.current.add(data.event_id);
    lastSequenceRef.current = data.sequence;
    setLastSequence(data.sequence);
    setEvents((prev) => [...prev, data].slice(-MAX_LIVE_EVENTS));
  }, [markRecoveryRequired]);

  useEffect(() => {
    const url = `${getBackendBaseUrl()}/api/v1/migrations/${runId}/events`;
    const source = new createEventSource(url);
    const listeners = new Map<string, EventListener>();

    source.onopen = () => setStatus((current) => (current === "recovering" ? "recovering" : "open"));
    source.onerror = () => {
      if (source.readyState === 2) {
        setStatus("closed");
      } else {
        setStatus("reconnecting");
      }
    };

    for (const type of WORKFLOW_EVENT_TYPES) {
      const listener = handleEvent as EventListener;
      listeners.set(type, listener);
      source.addEventListener(type, listener);
    }
    const replayUnavailableListener = (() => markRecoveryRequired()) as EventListener;
    listeners.set("replay_unavailable", replayUnavailableListener);
    source.addEventListener("replay_unavailable", replayUnavailableListener);

    return () => {
      for (const [type, listener] of listeners) {
        source.removeEventListener(type, listener);
      }
      source.close();
    };
  }, [runId, createEventSource, handleEvent, markRecoveryRequired]);

  return { status, events, lastSequence, recoveryRequired, clearRecoveryRequired };
}
