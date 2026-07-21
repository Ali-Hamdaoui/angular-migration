"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getBackendBaseUrl } from "@/api/client";
import { getAuthoritativeRunState } from "@/api/runs";
import type { AuthoritativeRunStateDto, WorkflowEventDto } from "@/types/generated/api";

export type AuthoritativeConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";

export const AUTHORITATIVE_EVENT_TYPES = ["RUN_CREATED", "RUN_START_ACCEPTED", "RUN_STARTED", "RUN_START_REJECTED", "SOURCE_INTAKE_QUEUED", "SOURCE_INTAKE_STARTED", "SOURCE_INTAKE_COMPLETED", "SOURCE_INTAKE_FAILED", "RUN_RECONSTRUCTED", "SNAPSHOT_STARTED", "SNAPSHOT_CREATED", "SNAPSHOT_FAILED", "SNAPSHOT_PROGRESS_UPDATED", "SNAPSHOT_QUARANTINED", "SOURCE_INTEGRITY_VERIFIED", "SOURCE_INTEGRITY_FAILED", "G02_CREATED", "G02_APPROVED", "G02_REJECTED", "G02_STALE", "ANALYSIS_AGENT_STARTED", "ANALYSIS_AGENT_COMPLETED", "ANALYSIS_AGENT_FAILED", "ANALYSIS_REVIEWER_STARTED", "ANALYSIS_REVIEWER_COMPLETED", "ANALYSIS_REVIEWER_FAILED", "G04_CREATED", "G04_APPROVED", "G04_MODIFICATION_REQUESTED", "G04_REJECTED", "G04_STALE", "COMPATIBILITY_RESOLUTION_STARTED", "COMPATIBILITY_RESOLUTION_COMPLETED", "COMPATIBILITY_RESOLUTION_BLOCKED", "G05_CREATED", "G05_APPROVED", "G05_MODIFICATION_REQUESTED", "G05_REJECTED", "G05_STALE", "MIGRATION_PLAN_CREATED", "STAGE_PLAN_CREATED", "PLAN_REVISION_CREATED", "APPROVAL_MARKED_STALE", "PLANNING_AGENT_COMPLETED", "G06_CREATED", "G06_APPROVED", "G06_MODIFICATION_REQUESTED", "G06_REJECTED", "G06_STALE", "COMMAND_QUEUED", "COMMAND_STARTED", "COMMAND_SUCCEEDED", "COMMAND_FAILED", "COMMAND_OUTPUT_AVAILABLE", "COMMAND_OUTPUT_CHUNK", "BASELINE_INSTALL_SUCCEEDED", "BASELINE_INSTALL_FAILED", "COMMAND_CANCELLED", "COMMAND_INTERRUPTED", "BASELINE_TARGETS_DISCOVERED", "BASELINE_BUILD_STARTED", "BASELINE_BUILD_COMPLETED", "BASELINE_TESTS_STARTED", "BASELINE_TESTS_COMPLETED", "BASELINE_LINT_STARTED", "BASELINE_LINT_COMPLETED", "BASELINE_FAILURES_FINGERPRINTED", "BASELINE_ROUTE_ANCHOR_CREATED", "BASELINE_BACKEND_ANCHOR_CREATED", "DISCOVERY_STARTED", "SCANNER_COMPLETED", "DISCOVERY_COMPLETED", "DISCOVERY_BLOCKED"] as const;

export const PARITY_BASELINE_EVENT_TYPES = ["PARITY_BASELINE_STARTED", "PARITY_BASELINE_COMPLETED", "PARITY_BASELINE_BLOCKED"] as const;
export const LLM_EVENT_TYPES = ['LLM_INVOCATION_STARTED', 'LLM_INVOCATION_COMPLETED', 'LLM_INVOCATION_FAILED', 'LLM_BUDGET_WARNING', 'LLM_BUDGET_BLOCKED'] as const;

export function useAuthoritativeRun(runId: string, initialState: AuthoritativeRunStateDto) {
  const [state, setState] = useState(initialState);
  const [status, setStatus] = useState<AuthoritativeConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const stateRef = useRef(initialState);
  const latestSequenceRef = useRef(Math.max(0, ...initialState.workflow_events.map((event) => event.sequence)));
  const seenEventIdsRef = useRef(new Set(initialState.workflow_events.map((event) => event.event_id)));
  const statusRef = useRef<AuthoritativeConnectionStatus>("connecting");
  const recoveryInProgressRef = useRef(false);

  const setConnectionStatus = useCallback((next: AuthoritativeConnectionStatus) => {
    statusRef.current = next;
    setStatus(next);
  }, []);

  const refresh = useCallback(() => {
    recoveryInProgressRef.current = true;
    setConnectionStatus("recovering");
    return getAuthoritativeRunState(runId)
      .then((next) => {
        const recovered = {
          ...next,
          workflow_events: [...next.workflow_events].sort((a, b) => a.sequence - b.sequence),
        };
        stateRef.current = recovered;
        latestSequenceRef.current = Math.max(0, ...recovered.workflow_events.map((event) => event.sequence));
        seenEventIdsRef.current = new Set(recovered.workflow_events.map((event) => event.event_id));
        setState(recovered);
        setError(null);
        recoveryInProgressRef.current = false;
        setConnectionStatus("open");
      })
      .catch(() => {
        setError("The authoritative run state could not be refreshed.");
        recoveryInProgressRef.current = false;
        setConnectionStatus("failed");
      });
  }, [runId, setConnectionStatus]);

  useEffect(() => {
    let active = true;
    const source = new EventSource(`${getBackendBaseUrl()}/api/v1/runs/${encodeURIComponent(runId)}/events`);
    const onEvent = (event: MessageEvent) => {
      try {
        const next = JSON.parse(event.data) as WorkflowEventDto;
        if (seenEventIdsRef.current.has(next.event_id) || next.sequence <= latestSequenceRef.current) return;
        if (next.sequence > latestSequenceRef.current + 1) {
          if (!recoveryInProgressRef.current) void refresh();
          return;
        }
        seenEventIdsRef.current.add(next.event_id);
        latestSequenceRef.current = next.sequence;
        const projected = { ...stateRef.current, workflow_events: [...stateRef.current.workflow_events, next].sort((a, b) => a.sequence - b.sequence), updated_at: next.occurred_at };
        stateRef.current = projected;
        setState(projected);
      } catch {
        setError("The backend sent an invalid run event.");
      }
    };
    source.onopen = () => {
      if (statusRef.current === "reconnecting" || recoveryInProgressRef.current) {
        void refresh();
      } else {
        setConnectionStatus("open");
      }
    };
    source.onerror = () => {
      if (active) {
        setConnectionStatus("reconnecting");
        if (!recoveryInProgressRef.current) void refresh();
      }
    };
    for (const type of [...AUTHORITATIVE_EVENT_TYPES, ...PARITY_BASELINE_EVENT_TYPES, ...LLM_EVENT_TYPES]) source.addEventListener(type, onEvent);
    const interval = window.setInterval(() => { void refresh(); }, 5000);
    void refresh();
    return () => {
      active = false;
      window.clearInterval(interval);
      for (const type of [...AUTHORITATIVE_EVENT_TYPES, ...PARITY_BASELINE_EVENT_TYPES, ...LLM_EVENT_TYPES]) source.removeEventListener(type, onEvent);
      source.close();
    };
  }, [refresh, runId, setConnectionStatus]);

  return { state, status, error, refresh };
}

